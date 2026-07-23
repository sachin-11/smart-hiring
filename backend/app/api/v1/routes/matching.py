import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.job import Job
from app.schemas.matching import MatchRequest, MatchResponse
from app.services import matching_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/match", tags=["matching"])


@router.post("", response_model=MatchResponse)
async def match_candidates(payload: MatchRequest, db: AsyncSession = Depends(get_db)) -> MatchResponse:
    job = await db.get(Job, payload.jd_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.description_embedding is None:
        raise HTTPException(status_code=400, detail="Job has not been analyzed yet (no embedding)")

    try:
        results = await matching_service.match_job_to_candidates(db, job, top_k=payload.top_k)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return MatchResponse(jd_id=job.id, results=results)
