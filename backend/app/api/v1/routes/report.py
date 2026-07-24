import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import report_agent
from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_recruiter
from app.core.rate_limit import limiter
from app.models.candidate import Candidate
from app.models.interview import Interview, InterviewStatus
from app.models.job import Application, Job
from app.models.report import Report
from app.schemas.report import (
    ReportDetailResponse,
    ReportGenerateRequest,
    ReportPdfResponse,
    ReportSchema,
    ReportShareRequest,
    ReportShareResponse,
)
from app.services import email_service, pdf_service, s3_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/report", tags=["report"], dependencies=[Depends(get_current_recruiter)])


async def _latest_match_score(db: AsyncSession, candidate_id: uuid.UUID, job_id: uuid.UUID) -> float | None:
    stmt = (
        select(Application.match_score)
        .where(Application.candidate_id == candidate_id, Application.job_id == job_id)
        .order_by(Application.applied_at.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


def _to_detail_response(report: Report, candidate_name: str | None, job_title: str | None) -> ReportDetailResponse:
    return ReportDetailResponse(
        report_id=report.id,
        interview_id=report.interview_id,
        candidate_id=report.candidate_id,
        job_id=report.job_id,
        candidate_name=candidate_name,
        job_title=job_title,
        created_at=report.created_at,
        report=ReportSchema.model_validate(report.report_data),
    )


@router.post("/generate", response_model=ReportDetailResponse)
@limiter.limit(settings.RATE_LIMIT_LLM_ENDPOINTS)
async def generate_report(
    request: Request, payload: ReportGenerateRequest, db: AsyncSession = Depends(get_db)
) -> ReportDetailResponse:
    interview = await db.get(Interview, payload.session_id)
    if interview is None:
        raise HTTPException(status_code=404, detail="Interview session not found")
    if interview.status != InterviewStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Interview is not completed yet")

    candidate = await db.get(Candidate, interview.candidate_id)
    job = await db.get(Job, interview.job_id)
    if candidate is None or job is None:
        raise HTTPException(status_code=404, detail="Candidate or job for this interview no longer exists")

    resume_data = {"skills": candidate.skills or [], "experience_years": candidate.experience_years}
    jd_data = {"title": job.title, "required_skills": job.required_skills or []}
    exchanges = (interview.ai_feedback or {}).get("exchanges", [])
    match_score = await _latest_match_score(db, candidate.id, job.id)

    try:
        report_schema = await report_agent.generate_report(resume_data, jd_data, exchanges, match_score)
    except Exception as exc:
        logger.exception("Report generation failed for interview=%s", interview.id)
        raise HTTPException(status_code=502, detail=f"Report generation failed: {exc}") from exc

    report = Report(
        id=uuid.uuid4(),
        interview_id=interview.id,
        candidate_id=candidate.id,
        job_id=job.id,
        report_data=report_schema.model_dump(),
        overall_score=report_schema.overall_score,
        recommendation=report_schema.recommendation,
    )

    try:
        pdf_bytes = pdf_service.build_report_pdf(report_schema, candidate.full_name, job.title)
        key, _ = await s3_service.upload_report_pdf(report.id, pdf_bytes)
        report.pdf_s3_key = key
    except Exception:
        logger.exception("PDF generation/upload failed for interview=%s; report will have no PDF", interview.id)

    db.add(report)
    await db.commit()
    await db.refresh(report)

    return _to_detail_response(report, candidate.full_name, job.title)


@router.get("/{report_id}", response_model=ReportDetailResponse)
async def get_report(report_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> ReportDetailResponse:
    report = await db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")

    candidate = await db.get(Candidate, report.candidate_id)
    job = await db.get(Job, report.job_id)
    return _to_detail_response(report, candidate.full_name if candidate else None, job.title if job else None)


@router.get("/{report_id}/pdf", response_model=ReportPdfResponse)
async def get_report_pdf(report_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> ReportPdfResponse:
    report = await db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    if report.pdf_s3_key is None:
        raise HTTPException(status_code=404, detail="No PDF was generated for this report")

    # Presigned URLs expire — regenerate fresh from the stored key on every call
    # rather than persisting a URL that could go stale.
    url = s3_service.generate_presigned_url(report.pdf_s3_key)
    return ReportPdfResponse(report_id=report.id, pdf_url=url)


@router.post("/{report_id}/share", response_model=ReportShareResponse)
async def share_report(
    report_id: uuid.UUID, payload: ReportShareRequest, db: AsyncSession = Depends(get_db)
) -> ReportShareResponse:
    report = await db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    if report.pdf_s3_key is None:
        raise HTTPException(status_code=400, detail="No PDF was generated for this report")

    candidate = await db.get(Candidate, report.candidate_id)
    job = await db.get(Job, report.job_id)
    pdf_url = s3_service.generate_presigned_url(report.pdf_s3_key)

    try:
        await email_service.send_report_share_email(
            payload.to_email,
            candidate.full_name if candidate else None,
            job.title if job else None,
            pdf_url,
            payload.message,
        )
    except email_service.EmailNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail="Email sharing is not configured on this server") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to send email: {exc}") from exc

    return ReportShareResponse(sent=True, detail=f"Report sent to {payload.to_email}")
