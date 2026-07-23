import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.jd_analyzer import JDAnalyzerAgent
from app.core.database import get_db
from app.models.job import Application, Job, JobStatus
from app.schemas.job import JobCreateRequest, JobDetailResponse, JobListItem, JobListResponse
from app.services import embedding_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs", tags=["jobs"])

_jd_agent: JDAnalyzerAgent | None = None


def get_jd_agent() -> JDAnalyzerAgent:
    global _jd_agent
    if _jd_agent is None:
        _jd_agent = JDAnalyzerAgent()
    return _jd_agent


@router.post("", response_model=JobDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_job(payload: JobCreateRequest, db: AsyncSession = Depends(get_db)) -> JobDetailResponse:
    job = Job(
        id=uuid.uuid4(),
        title=payload.title,
        description=payload.description,
        department=payload.department,
        location=payload.location,
        employment_type=payload.employment_type,
        min_experience=payload.min_experience,
        max_experience=payload.max_experience,
        required_skills=payload.required_skills or None,
        status=JobStatus.DRAFT,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # JD analysis (incl. the embedding matching depends on) runs synchronously:
    # the frontend auto-triggers matching right after this call returns, so the
    # embedding must already exist by then — unlike resume parsing, this isn't backgrounded.
    try:
        agent = get_jd_agent()
        analysis = await agent.analyze(payload.description)

        if not job.required_skills:
            job.required_skills = analysis.required_skills or None
        job.nice_to_have_skills = analysis.nice_to_have or None
        job.responsibilities = analysis.responsibilities or None
        job.seniority_level = analysis.seniority_level

        embedding = await embedding_service.generate_embedding(payload.description)
        job.description_embedding = embedding
        job.status = JobStatus.OPEN

        await db.commit()
        await db.refresh(job)
    except Exception:
        logger.exception("JD analysis failed for job %s; job created but not analyzed", job.id)
        await db.rollback()
        job = await db.get(Job, job.id)

    return JobDetailResponse.model_validate(job)


@router.get("", response_model=JobListResponse)
async def list_jobs(db: AsyncSession = Depends(get_db)) -> JobListResponse:
    stmt = (
        select(
            Job,
            func.count(Application.id).label("applicant_count"),
            func.max(Application.match_score).label("top_match_score"),
        )
        .outerjoin(Application, Application.job_id == Job.id)
        .group_by(Job.id)
        .order_by(Job.created_at.desc())
    )
    rows = (await db.execute(stmt)).all()
    jobs = [
        JobListItem(
            id=job.id,
            title=job.title,
            department=job.department,
            location=job.location,
            status=job.status,
            applicant_count=applicant_count,
            top_match_score=top_match_score,
            created_at=job.created_at,
        )
        for job, applicant_count, top_match_score in rows
    ]
    return JobListResponse(jobs=jobs)


@router.get("/{job_id}", response_model=JobDetailResponse)
async def get_job(job_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> JobDetailResponse:
    job = await db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobDetailResponse.model_validate(job)
