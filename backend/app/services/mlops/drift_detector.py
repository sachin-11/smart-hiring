"""Embedding-distribution drift detection for resume embeddings.

Not built on Evidently AI — see MODULE_7_SETUP.md for why (a real, verified
dependency conflict between evidently's litestar-based UI server and FastAPI's
own `python-multipart` dependency, which broke file uploads when both were
installed). PSI (Population Stability Index) is implemented directly instead;
it's a well-defined, standard formula and doesn't need a monitoring framework
just to compute it.
"""

import json
import logging
import math
import uuid
from datetime import datetime, timezone

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.candidate import Candidate, ParsingStatus
from app.models.mlops import DriftReport
from app.services import s3_service
from app.services.mlops import experiment_tracker

logger = logging.getLogger(__name__)

DEFAULT_BASELINE_SIZE = 100
DEFAULT_CURRENT_SIZE = 50
MIN_BASELINE_SIZE = 10
PSI_BUCKETS = 10
PSI_ALERT_THRESHOLD = 0.2
_EPSILON = 1e-6


def compute_psi(baseline: np.ndarray, current: np.ndarray, buckets: int = PSI_BUCKETS) -> float:
    """Population Stability Index between two 1-D score distributions.

    Bin edges are derived from the *baseline* distribution's quantiles (standard
    PSI methodology), then both distributions are binned against those same edges.
    """
    if len(baseline) == 0 or len(current) == 0:
        raise ValueError("Both baseline and current arrays must be non-empty")

    quantiles = np.linspace(0, 1, buckets + 1)
    edges = np.unique(np.quantile(baseline, quantiles))
    if len(edges) < 3:
        # Baseline has near-zero variance (e.g. all identical embeddings) — can't
        # meaningfully bucket it; treat as no drift rather than dividing by zero.
        return 0.0
    edges[0], edges[-1] = -np.inf, np.inf

    baseline_counts, _ = np.histogram(baseline, bins=edges)
    current_counts, _ = np.histogram(current, bins=edges)

    baseline_pct = baseline_counts / len(baseline) + _EPSILON
    current_pct = current_counts / len(current) + _EPSILON

    return float(np.sum((current_pct - baseline_pct) * np.log(current_pct / baseline_pct)))


def _embedding_similarity_scores(embeddings: list[list[float]], centroid: np.ndarray) -> np.ndarray:
    """Reduces each high-dimensional embedding to a single scalar — cosine similarity
    to the baseline centroid — so PSI (a 1-D technique) can be applied to embeddings.
    A drop in this score distribution means incoming resumes look less like the
    baseline population, which is exactly the kind of drift PSI is meant to catch."""
    matrix = np.array(embeddings)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    normalized = matrix / np.clip(norms, 1e-9, None)
    centroid_normalized = centroid / max(np.linalg.norm(centroid), 1e-9)
    return normalized @ centroid_normalized


async def run_drift_check(
    db: AsyncSession,
    baseline_size: int = DEFAULT_BASELINE_SIZE,
    current_size: int = DEFAULT_CURRENT_SIZE,
) -> dict:
    baseline_stmt = (
        select(Candidate)
        .where(Candidate.resume_embedding.is_not(None))
        .where(Candidate.parsing_status == ParsingStatus.COMPLETED)
        .order_by(Candidate.created_at.asc())
        .limit(baseline_size)
    )
    baseline_candidates = list((await db.execute(baseline_stmt)).scalars().all())

    if len(baseline_candidates) < MIN_BASELINE_SIZE:
        raise ValueError(
            f"Need at least {MIN_BASELINE_SIZE} parsed resumes with embeddings to establish a "
            f"baseline; found {len(baseline_candidates)}."
        )

    baseline_cutoff_id = baseline_candidates[-1].id
    baseline_cutoff_created_at = baseline_candidates[-1].created_at

    current_stmt = (
        select(Candidate)
        .where(Candidate.resume_embedding.is_not(None))
        .where(Candidate.parsing_status == ParsingStatus.COMPLETED)
        .where(Candidate.created_at > baseline_cutoff_created_at)
        .where(Candidate.id != baseline_cutoff_id)
        .order_by(Candidate.created_at.desc())
        .limit(current_size)
    )
    current_candidates = list((await db.execute(current_stmt)).scalars().all())

    if not current_candidates:
        raise ValueError("No candidates added after the baseline window yet; nothing to compare.")

    baseline_embeddings = [c.resume_embedding for c in baseline_candidates]
    current_embeddings = [c.resume_embedding for c in current_candidates]

    centroid = np.mean(np.array(baseline_embeddings), axis=0)
    baseline_scores = _embedding_similarity_scores(baseline_embeddings, centroid)
    current_scores = _embedding_similarity_scores(current_embeddings, centroid)

    psi = compute_psi(baseline_scores, current_scores)
    alert = psi > PSI_ALERT_THRESHOLD
    if math.isnan(psi):
        psi = 0.0

    if alert:
        logger.warning(
            "Embedding drift detected: PSI=%.4f exceeds threshold %.2f (baseline=%d, current=%d)",
            psi,
            PSI_ALERT_THRESHOLD,
            len(baseline_candidates),
            len(current_candidates),
        )

    report_id = uuid.uuid4()
    report_payload = {
        "report_id": str(report_id),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "baseline_size": len(baseline_candidates),
        "current_size": len(current_candidates),
        "psi_score": psi,
        "alert_triggered": alert,
        "psi_threshold": PSI_ALERT_THRESHOLD,
        "baseline_score_summary": {
            "mean": float(np.mean(baseline_scores)),
            "std": float(np.std(baseline_scores)),
        },
        "current_score_summary": {
            "mean": float(np.mean(current_scores)),
            "std": float(np.std(current_scores)),
        },
    }

    s3_key = None
    try:
        s3_key, _ = await s3_service.upload_drift_report(report_id, json.dumps(report_payload, indent=2).encode())
    except Exception:
        logger.exception("Failed to upload drift report %s to S3", report_id)

    row = DriftReport(
        id=report_id,
        baseline_size=len(baseline_candidates),
        current_size=len(current_candidates),
        psi_score=psi,
        alert_triggered=alert,
        s3_key=s3_key,
    )
    db.add(row)
    await db.commit()

    try:
        await experiment_tracker.log_drift_check(psi, alert, len(baseline_candidates), len(current_candidates))
    except Exception:
        logger.exception("Failed to log drift check %s to MLflow", report_id)

    return report_payload
