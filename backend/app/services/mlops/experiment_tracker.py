"""MLflow experiment tracking: prompt versions, match score distributions per JD,
and token usage/cost per pipeline run.

MLflow's client is synchronous (local file-store I/O); calls are wrapped in
asyncio.to_thread so they don't block the event loop, matching how the rest of
this codebase wraps other sync clients (boto3 in s3_service.py).
"""

import asyncio
import logging
import tempfile
import uuid
from pathlib import Path

import mlflow

from app.core.config import settings

logger = logging.getLogger(__name__)

EXPERIMENT_PIPELINE_RUNS = "hiring-pipeline-runs"
EXPERIMENT_PROMPTS = "prompt-versions"
EXPERIMENT_RAGAS = "ragas-evaluations"
EXPERIMENT_DRIFT = "embedding-drift"

_configured = False


def _ensure_configured() -> None:
    global _configured
    if not _configured:
        mlflow.set_tracking_uri(settings.MLFLOW_TRACKING_URI)
        _configured = True


def _log_pipeline_run_sync(
    candidate_id: str, job_id: str, match_score: float | None, token_costs: dict[str, float], total_cost: float
) -> str:
    _ensure_configured()
    mlflow.set_experiment(EXPERIMENT_PIPELINE_RUNS)
    with mlflow.start_run(run_name=f"pipeline-{job_id[:8]}-{candidate_id[:8]}") as run:
        mlflow.set_tags({"candidate_id": candidate_id, "job_id": job_id})
        if match_score is not None:
            mlflow.log_metric("match_score", match_score)
        for model, cost in token_costs.items():
            mlflow.log_metric(f"cost_usd.{model}", cost)
        mlflow.log_metric("cost_usd.total", total_cost)
        return run.info.run_id


async def log_pipeline_run(
    candidate_id: uuid.UUID, job_id: uuid.UUID, match_score: float | None, token_costs: dict[str, float]
) -> str:
    total_cost = sum(token_costs.values())
    return await asyncio.to_thread(
        _log_pipeline_run_sync, str(candidate_id), str(job_id), match_score, token_costs, total_cost
    )


def _log_prompt_version_sync(name: str, template_text: str, version: str) -> str:
    _ensure_configured()
    mlflow.set_experiment(EXPERIMENT_PROMPTS)
    with mlflow.start_run(run_name=f"{name}-{version}") as run:
        mlflow.set_tags({"prompt_name": name, "version": version})
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "prompt_template.txt"
            path.write_text(template_text, encoding="utf-8")
            mlflow.log_artifact(str(path))
        return run.info.run_id


async def log_prompt_version(name: str, template_text: str, version: str = "v1") -> str:
    """Logs a prompt template as an MLflow artifact — call this whenever a prompt
    used in production (question generation, report generation, ...) changes, so
    prompt history is auditable alongside the metrics it produced."""
    return await asyncio.to_thread(_log_prompt_version_sync, name, template_text, version)


def _log_ragas_run_sync(run_id: str, metrics: dict[str, float], alert: bool) -> str:
    _ensure_configured()
    mlflow.set_experiment(EXPERIMENT_RAGAS)
    with mlflow.start_run(run_name=f"ragas-{run_id[:8]}") as run:
        mlflow.set_tags({"eval_run_id": run_id, "alert_triggered": str(alert)})
        for key, value in metrics.items():
            mlflow.log_metric(key, value)
        return run.info.run_id


async def log_ragas_run(run_id: uuid.UUID, metrics: dict[str, float], alert: bool) -> str:
    return await asyncio.to_thread(_log_ragas_run_sync, str(run_id), metrics, alert)


def _log_drift_check_sync(psi_score: float, alert: bool, baseline_size: int, current_size: int) -> str:
    _ensure_configured()
    mlflow.set_experiment(EXPERIMENT_DRIFT)
    with mlflow.start_run() as run:
        mlflow.set_tags({"alert_triggered": str(alert)})
        mlflow.log_metric("psi_score", psi_score)
        mlflow.log_metric("baseline_size", baseline_size)
        mlflow.log_metric("current_size", current_size)
        return run.info.run_id


async def log_drift_check(psi_score: float, alert: bool, baseline_size: int, current_size: int) -> str:
    return await asyncio.to_thread(_log_drift_check_sync, psi_score, alert, baseline_size, current_size)


def _get_pipeline_run_stats_sync() -> dict:
    _ensure_configured()
    experiment = mlflow.get_experiment_by_name(EXPERIMENT_PIPELINE_RUNS)
    if experiment is None:
        return {"count": 0, "avg_match_score": None, "total_cost_usd": 0.0}

    runs = mlflow.search_runs(experiment_ids=[experiment.experiment_id])
    if runs.empty:
        return {"count": 0, "avg_match_score": None, "total_cost_usd": 0.0}

    avg_match_score = None
    if "metrics.match_score" in runs.columns:
        scores = runs["metrics.match_score"].dropna()
        if not scores.empty:
            avg_match_score = float(scores.mean())

    total_cost = 0.0
    if "metrics.cost_usd.total" in runs.columns:
        total_cost = float(runs["metrics.cost_usd.total"].dropna().sum())

    return {"count": len(runs), "avg_match_score": avg_match_score, "total_cost_usd": total_cost}


async def get_pipeline_run_stats() -> dict:
    """Aggregate stats across all logged pipeline runs, for the analytics dashboard."""
    try:
        return await asyncio.to_thread(_get_pipeline_run_stats_sync)
    except Exception:
        logger.exception("Failed to query MLflow for pipeline run stats")
        return {"count": 0, "avg_match_score": None, "total_cost_usd": 0.0}
