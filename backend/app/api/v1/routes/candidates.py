import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_recruiter
from app.models.candidate import Candidate, CandidateStatus
from app.models.interview import Interview
from app.models.job import Application, ApplicationStatus, Job
from app.models.report import Report
from app.schemas.candidate import (
    BulkActionResponse,
    BulkEmailRequest,
    BulkShortlistRequest,
    CandidateDeleteResponse,
    CandidateListItem,
    CandidateListResponse,
)
from app.services import notification_queue, s3_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/candidates", tags=["candidates"], dependencies=[Depends(get_current_recruiter)])


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
    # Each candidate's most recent application (if any) drives the "applied JD" /
    # "match score" columns. A LATERAL join computes it per-candidate directly in
    # SQL — needed so min_score/max_score filtering and LIMIT/OFFSET can both run
    # at the DB level instead of pulling every candidate into Python first.
    latest_application = (
        select(
            Application.match_score.label("match_score"),
            Job.id.label("job_id"),
            Job.title.label("job_title"),
        )
        .join(Job, Job.id == Application.job_id)
        .where(Application.candidate_id == Candidate.id)
        .order_by(Application.applied_at.desc())
        .limit(1)
        .correlate(Candidate)
        .subquery()
        .lateral()
    )

    base_stmt = select(Candidate, latest_application.c.match_score, latest_application.c.job_title, latest_application.c.job_id).outerjoin(
        latest_application, true()
    )
    if status is not None:
        base_stmt = base_stmt.where(Candidate.status == status)
    if skill is not None:
        base_stmt = base_stmt.where(Candidate.skills.any(skill))
    if min_score is not None:
        base_stmt = base_stmt.where(latest_application.c.match_score >= min_score)
    if max_score is not None:
        base_stmt = base_stmt.where(latest_application.c.match_score <= max_score)

    total = (await db.execute(select(func.count()).select_from(base_stmt.subquery()))).scalar_one()

    page_stmt = base_stmt.order_by(Candidate.created_at.desc()).limit(limit).offset(offset)
    rows = (await db.execute(page_stmt)).all()

    items = [
        CandidateListItem(
            id=candidate.id,
            full_name=candidate.full_name,
            email=candidate.email,
            status=candidate.status,
            skills=candidate.skills or [],
            applied_job_title=job_title,
            applied_job_id=job_id,
            match_score=match_score,
            created_at=candidate.created_at,
        )
        for candidate, match_score, job_title, job_id in rows
    ]

    return CandidateListResponse(candidates=items, total=total)


@router.post("/bulk-shortlist", response_model=BulkActionResponse)
async def bulk_shortlist(
    payload: BulkShortlistRequest,
    db: AsyncSession = Depends(get_db),
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


@router.delete("/{candidate_id}", response_model=CandidateDeleteResponse)
async def delete_candidate(
    candidate_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> CandidateDeleteResponse:
    """Permanently deletes a candidate and all their data (DB rows + S3
    objects) — for GDPR-style "right to be forgotten" requests. Interview
    audio, resume files, and report PDFs are removed by S3 key prefix since
    individual object keys aren't tracked anywhere else. DB rows for
    applications/interviews/reports cascade-delete automatically via FK
    ondelete="CASCADE", so we only need to look them up (before the delete)
    to know which S3 prefixes to clean up."""
    candidate = await db.get(Candidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")

    interview_ids = (
        (await db.execute(select(Interview.id).where(Interview.candidate_id == candidate_id))).scalars().all()
    )
    report_ids = (
        (await db.execute(select(Report.id).where(Report.candidate_id == candidate_id))).scalars().all()
    )

    s3_objects_deleted = await s3_service.delete_prefix(s3_service.build_resume_prefix(candidate_id))
    for interview_id in interview_ids:
        s3_objects_deleted += await s3_service.delete_prefix(s3_service.build_interview_prefix(interview_id))
    for report_id in report_ids:
        s3_objects_deleted += await s3_service.delete_prefix(s3_service.build_report_prefix(report_id))

    await db.delete(candidate)
    await db.commit()

    logger.info(
        "Deleted candidate %s (interviews=%d, reports=%d, s3_objects=%d)",
        candidate_id,
        len(interview_ids),
        len(report_ids),
        s3_objects_deleted,
    )
    return CandidateDeleteResponse(
        candidate_id=candidate_id,
        interviews_deleted=len(interview_ids),
        reports_deleted=len(report_ids),
        s3_objects_deleted=s3_objects_deleted,
    )
