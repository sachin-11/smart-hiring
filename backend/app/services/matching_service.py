import asyncio
import logging
import math
import re
import uuid

from langchain_openai import ChatOpenAI
from pydantic import BaseModel
from rank_bm25 import BM25Okapi
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.candidate import Candidate, ParsingStatus
from app.models.job import Job
from app.schemas.matching import MatchResult

logger = logging.getLogger(__name__)

DENSE_TOP_K = 20
SPARSE_TOP_K = 20
RRF_K = 60
CANDIDATE_POOL_LIMIT = 1000
CROSS_ENCODER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


# --- Dense search (pgvector cosine similarity) ---------------------------------


async def _dense_search(
    session: AsyncSession, jd_embedding: list[float], limit: int = DENSE_TOP_K
) -> list[Candidate]:
    stmt = (
        select(Candidate)
        .where(Candidate.resume_embedding.is_not(None))
        .where(Candidate.parsing_status == ParsingStatus.COMPLETED)
        .order_by(Candidate.resume_embedding.cosine_distance(jd_embedding))
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


# --- Sparse search (BM25) -------------------------------------------------------


async def _fetch_candidate_pool(session: AsyncSession, limit: int = CANDIDATE_POOL_LIMIT) -> list[Candidate]:
    stmt = (
        select(Candidate)
        .where(Candidate.parsing_status == ParsingStatus.COMPLETED)
        .where(Candidate.resume_text.is_not(None))
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


def _sparse_search_sync(pool: list[Candidate], query_text: str, limit: int) -> list[Candidate]:
    if not pool:
        return []
    corpus = [_tokenize(c.resume_text or "") for c in pool]
    bm25 = BM25Okapi(corpus)
    scores = bm25.get_scores(_tokenize(query_text))
    ranked_idx = sorted(range(len(pool)), key=lambda i: scores[i], reverse=True)[:limit]
    return [pool[i] for i in ranked_idx]


async def _sparse_search(pool: list[Candidate], query_text: str, limit: int = SPARSE_TOP_K) -> list[Candidate]:
    return await asyncio.to_thread(_sparse_search_sync, pool, query_text, limit)


# --- Reciprocal Rank Fusion ------------------------------------------------------


def _reciprocal_rank_fusion(
    dense: list[Candidate], sparse: list[Candidate], k: int = RRF_K
) -> list[tuple[Candidate, float]]:
    scores: dict[uuid.UUID, float] = {}
    by_id: dict[uuid.UUID, Candidate] = {}

    for rank, candidate in enumerate(dense, start=1):
        by_id[candidate.id] = candidate
        scores[candidate.id] = scores.get(candidate.id, 0.0) + 1.0 / (k + rank)

    for rank, candidate in enumerate(sparse, start=1):
        by_id[candidate.id] = candidate
        scores[candidate.id] = scores.get(candidate.id, 0.0) + 1.0 / (k + rank)

    fused = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    return [(by_id[candidate_id], score) for candidate_id, score in fused]


# --- Cross-encoder reranking -----------------------------------------------------

_cross_encoder = None


def _get_cross_encoder():
    global _cross_encoder
    if _cross_encoder is None:
        from sentence_transformers import CrossEncoder

        logger.info("Loading cross-encoder model %s (first use only)...", CROSS_ENCODER_MODEL)
        _cross_encoder = CrossEncoder(CROSS_ENCODER_MODEL)
    return _cross_encoder


def _cross_encoder_rerank_sync(jd_text: str, candidates: list[Candidate]) -> list[tuple[Candidate, float]]:
    if not candidates:
        return []
    model = _get_cross_encoder()
    pairs = [(jd_text, candidate.resume_text or "") for candidate in candidates]
    raw_scores = model.predict(pairs)
    probabilities = [1 / (1 + math.exp(-float(s))) for s in raw_scores]
    ranked = sorted(zip(candidates, probabilities), key=lambda cp: cp[1], reverse=True)
    return ranked


async def _cross_encoder_rerank(jd_text: str, candidates: list[Candidate]) -> list[tuple[Candidate, float]]:
    return await asyncio.to_thread(_cross_encoder_rerank_sync, jd_text, candidates)


# --- LLM-generated match explanations --------------------------------------------


class _ExplanationItem(BaseModel):
    candidate_id: uuid.UUID
    explanation: str


class _ExplanationBatch(BaseModel):
    explanations: list[_ExplanationItem]


_explanation_llm = None

_DEFAULT_EXPLANATION = "Ranked highly by semantic and keyword match against the job description."


def _get_explanation_llm():
    global _explanation_llm
    if _explanation_llm is None:
        base_llm = ChatOpenAI(model="gpt-4o", temperature=0, api_key=settings.OPENAI_API_KEY)
        _explanation_llm = base_llm.with_structured_output(_ExplanationBatch)
    return _explanation_llm


async def _generate_explanations(job: Job, candidates: list[Candidate]) -> dict[uuid.UUID, str]:
    if not candidates:
        return {}

    candidate_lines = "\n".join(
        f"- id={candidate.id}, name={candidate.full_name or 'Unknown'}, "
        f"skills={', '.join(candidate.skills or []) or 'none listed'}, "
        f"experience={candidate.experience_years if candidate.experience_years is not None else '?'} yrs"
        for candidate in candidates
    )
    prompt = (
        f"Job title: {job.title}\n"
        f"Required skills: {', '.join(job.required_skills or []) or 'none specified'}\n"
        f"Responsibilities: {', '.join(job.responsibilities or []) or 'none specified'}\n\n"
        f"Candidates:\n{candidate_lines}\n\n"
        "For each candidate listed above, write one concise sentence (max 30 words) explaining "
        "why they are a good or partial match for this job. Only reference skills explicitly "
        "listed for that candidate above — do not assume or invent skills they aren't listed as "
        "having, even if the job requires them. If they're missing a required skill, you may say "
        "so. Return one explanation per candidate id."
    )

    try:
        llm = _get_explanation_llm()
        result: _ExplanationBatch = await llm.ainvoke(prompt)
        return {item.candidate_id: item.explanation for item in result.explanations}
    except Exception:
        logger.exception("Failed to generate match explanations; falling back to a default message")
        return {}


# --- Skill diffing -----------------------------------------------------------------


def _diff_skills(required: list[str] | None, candidate_skills: list[str] | None) -> tuple[list[str], list[str]]:
    required = required or []
    candidate_lower = {s.lower() for s in (candidate_skills or [])}

    overlap: list[str] = []
    missing: list[str] = []
    for skill in required:
        (overlap if skill.lower() in candidate_lower else missing).append(skill)
    return overlap, missing


# --- Orchestration -------------------------------------------------------------------


async def match_job_to_candidates(session: AsyncSession, job: Job, top_k: int = 10) -> list[MatchResult]:
    if job.description_embedding is None:
        raise ValueError("Job has no description embedding yet; it hasn't been analyzed")

    dense_results, pool = await asyncio.gather(
        _dense_search(session, job.description_embedding, limit=DENSE_TOP_K),
        _fetch_candidate_pool(session),
    )
    sparse_results = await _sparse_search(pool, job.description, limit=SPARSE_TOP_K)

    if not dense_results and not sparse_results:
        return []

    fused = _reciprocal_rank_fusion(dense_results, sparse_results, k=RRF_K)
    top_fused = [candidate for candidate, _ in fused[:top_k]]

    reranked = await _cross_encoder_rerank(job.description, top_fused)
    explanations = await _generate_explanations(job, [candidate for candidate, _ in reranked])

    results: list[MatchResult] = []
    for candidate, score in reranked:
        overlap, missing = _diff_skills(job.required_skills, candidate.skills)
        results.append(
            MatchResult(
                candidate_id=candidate.id,
                name=candidate.full_name,
                match_score=round(score * 100, 1),
                skill_overlap=overlap,
                missing_skills=missing,
                explanation=explanations.get(candidate.id, _DEFAULT_EXPLANATION),
            )
        )
    return results
