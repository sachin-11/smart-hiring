import logging
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_recruiter
from app.models.candidate import Candidate, CandidateStatus
from app.models.job import Application, ApplicationStatus, Job
from app.models.recruiter import Recruiter
from app.schemas.candidate import (
    BulkActionResponse,
    BulkEmailRequest,
    BulkShortlistRequest,
    CandidateListItem,
    CandidateListResponse,
)
from app.services import notification_queue

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/candidates", tags=["candidates"])


@router.get("", response_model=CandidateListResponse)
async def list_candidates(
    status: CandidateStatus | None = None,
    skill: str | None = None,
    min_score: float | None = Query(default=None, ge=0, le=100),
    max_score: float | None = Query(default=None, ge=0, le=100),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> CandidateListResponse:
    stmt = select(Candidate)
    if status is not None:
        stmt = stmt.where(Candidate.status == status)
    if skill is not None:
        stmt = stmt.where(Candidate.skills.any(skill))
    stmt = stmt.order_by(Candidate.created_at.desc())

    all_candidates = list((await db.execute(stmt)).scalars().all())
    candidate_ids = [c.id for c in all_candidates]

    # Each candidate's most recent application (if any) drives the "applied JD" /
    # "match score" columns — fetched separately and merged in Python rather than a
    # correlated-subquery join, since this is a small admin list, not a hot path.
    latest_application_by_candidate: dict[uuid.UUID, tuple[Application, Job]] = {}
    if candidate_ids:
        app_stmt = (
            select(Application, Job)
            .join(Job, Job.id == Application.job_id)
            .where(Application.candidate_id.in_(candidate_ids))
            .order_by(Application.candidate_id, Application.applied_at.desc())
        )
        for application, job in (await db.execute(app_stmt)).all():
            if application.candidate_id not in latest_application_by_candidate:
                latest_application_by_candidate[application.candidate_id] = (application, job)

    items = []
    for candidate in all_candidates:
        application, job = latest_application_by_candidate.get(candidate.id, (None, None))
        match_score = application.match_score if application else None

        if min_score is not None and (match_score is None or match_score < min_score):
            continue
        if max_score is not None and (match_score is None or match_score > max_score):
            continue

        items.append(
            CandidateListItem(
                id=candidate.id,
                full_name=candidate.full_name,
                email=candidate.email,
                status=candidate.status,
                skills=candidate.skills or [],
                applied_job_title=job.title if job else None,
                applied_job_id=job.id if job else None,
                match_score=match_score,
                created_at=candidate.created_at,
            )
        )

    total = len(items)
    return CandidateListResponse(candidates=items[offset : offset + limit], total=total)


@router.post("/bulk-shortlist", response_model=BulkActionResponse)
async def bulk_shortlist(
    payload: BulkShortlistRequest,
    db: AsyncSession = Depends(get_db),
    _recruiter: Recruiter = Depends(get_current_recruiter),
) -> BulkActionResponse:
    """Shortlists each candidate's most recent application. Candidates with no
    application yet are skipped — there's nothing to shortlist them for."""
    affected = 0
    for candidate_id in payload.candidate_ids:
        stmt = (
            select(Application)
            .where(Application.candidate_id == candidate_id)
            .order_by(Application.applied_at.desc())
            .limit(1)
        )
        application = (await db.execute(stmt)).scalar_one_or_none()
        if application is None:
            continue
        application.status = ApplicationStatus.SHORTLISTED
        affected += 1

    await db.commit()
    return BulkActionResponse(affected=affected)


@router.post("/bulk-email", response_model=BulkActionResponse)
async def bulk_email(
    payload: BulkEmailRequest,
    db: AsyncSession = Depends(get_db),
    _recruiter: Recruiter = Depends(get_current_recruiter),
) -> BulkActionResponse:
    job = await db.get(Job, payload.job_id)
    if job is None:
        return BulkActionResponse(affected=0)

    affected = 0
    for candidate_id in payload.candidate_ids:
        candidate = await db.get(Candidate, candidate_id)
        if candidate is None or not candidate.email:
            continue
        await notification_queue.enqueue(
            {
                "type": "shortlist_email",
                "to_email": candidate.email,
                "candidate_name": candidate.full_name,
                "job_title": job.title,
                "message": payload.message,
            }
        )
        affected += 1

    await notification_queue.drain_queue()
    return BulkActionResponse(affected=affected)
