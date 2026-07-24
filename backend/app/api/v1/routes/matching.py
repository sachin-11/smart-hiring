import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import cache_service
from app.core.database import get_db
from app.core.deps import get_current_recruiter
from app.models.job import Job
from app.schemas.matching import MatchRequest, MatchResponse, MatchResult
from app.services import matching_service
from app.services.monitoring import match_score_distribution

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/match", tags=["matching"], dependencies=[Depends(get_current_recruiter)])


@router.post("", response_model=MatchResponse)
async def match_candidates(payload: MatchRequest, db: AsyncSession = Depends(get_db)) -> MatchResponse:
    job = await db.get(Job, payload.jd_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.description_embedding is None:
        raise HTTPException(status_code=400, detail="Job has not been analyzed yet (no embedding)")

    # Cache-aside: the hybrid search + cross-encoder rerank behind this endpoint is
    # the slowest call in the app (can take up to a minute cold) — cache the result
    # for repeated lookups of the same job/top_k within the TTL window.
    cached = await cache_service.get_cached_match_results(job.id, payload.top_k)
    if cached is not None:
        results = [MatchResult(**r) for r in cached]
    else:
        try:
            results = await matching_service.match_job_to_candidates(db, job, top_k=payload.top_k)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        await cache_service.set_cached_match_results(job.id, payload.top_k, [r.model_dump(mode="json") for r in results])

    for result in results:
        match_score_distribution.observe(result.match_score)

    return MatchResponse(jd_id=job.id, results=results)
