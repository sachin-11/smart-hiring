import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.resume_parser import ResumeParserAgent
from app.core.database import get_db, get_db_context
from app.models.candidate import Candidate, ParsingStatus
from app.models.interview import Interview
from app.models.job import Application
from app.schemas.resume import ResumeDetailResponse, ResumeStatusResponse, ResumeUploadResponse
from app.services import embedding_service, s3_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/resume", tags=["resume"])

ALLOWED_EXTENSIONS = {"pdf", "docx"}
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024

_parser_agent: ResumeParserAgent | None = None


def get_parser_agent() -> ResumeParserAgent:
    global _parser_agent
    if _parser_agent is None:
        _parser_agent = ResumeParserAgent()
    return _parser_agent


@router.post("/upload", response_model=ResumeUploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_resume(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> ResumeUploadResponse:
    filename = file.filename or ""
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Only PDF and DOCX resumes are supported")

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if len(contents) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="Resume file exceeds the 10MB size limit")

    candidate = Candidate(
        id=uuid.uuid4(),
        original_filename=filename,
        parsing_status=ParsingStatus.PENDING,
    )
    db.add(candidate)
    await db.commit()
    await db.refresh(candidate)

    background_tasks.add_task(_process_resume, candidate.id, contents, filename)

    return ResumeUploadResponse(candidate_id=candidate.id, status=candidate.parsing_status)


@router.get("/{candidate_id}/status", response_model=ResumeStatusResponse)
async def get_resume_status(
    candidate_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> ResumeStatusResponse:
    candidate = await db.get(Candidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return ResumeStatusResponse(
        candidate_id=candidate.id, status=candidate.parsing_status, error=candidate.parsing_error
    )


@router.get("/{candidate_id}", response_model=ResumeDetailResponse)
async def get_resume(candidate_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> ResumeDetailResponse:
    candidate = await db.get(Candidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return ResumeDetailResponse.model_validate(candidate)


async def _reconcile_existing_email(session: AsyncSession, new_candidate_id: uuid.UUID, email: str) -> None:
    """A resume re-upload creates a fresh candidate row before parsing knows
    the email, so a second upload from the same person collides with their
    existing row on the unique email constraint. Treat it as a refresh:
    re-point any applications/interviews to the new row and drop the stale one.
    """
    stmt = select(Candidate).where(Candidate.email == email, Candidate.id != new_candidate_id)
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing is None:
        return

    logger.info(
        "Resume re-upload for %s: merging into candidate %s, removing old row %s",
        email,
        new_candidate_id,
        existing.id,
    )
    await session.execute(
        update(Application).where(Application.candidate_id == existing.id).values(candidate_id=new_candidate_id)
    )
    await session.execute(
        update(Interview).where(Interview.candidate_id == existing.id).values(candidate_id=new_candidate_id)
    )
    await session.delete(existing)
    await session.flush()


async def _process_resume(candidate_id: uuid.UUID, contents: bytes, filename: str) -> None:
    """Background task: uploads to S3, parses the resume, generates + stores its embedding.

    Runs after the HTTP response is sent, so it needs its own DB session —
    the request-scoped session from `get_db` is already closed by then.
    """
    async with get_db_context() as session:
        candidate = await session.get(Candidate, candidate_id)
        if candidate is None:
            logger.error("Candidate %s disappeared before background processing started", candidate_id)
            return

        candidate.parsing_status = ParsingStatus.PROCESSING
        await session.commit()

        try:
            s3_key, object_url = await s3_service.upload_resume_file(candidate_id, filename, contents)
            agent = get_parser_agent()
            raw_text, parsed = await agent.parse(contents, filename)

            if parsed.email:
                await _reconcile_existing_email(session, candidate_id, parsed.email)

            candidate.s3_key = s3_key
            candidate.resume_url = object_url
            candidate.resume_text = raw_text
            candidate.full_name = parsed.name
            candidate.email = parsed.email
            candidate.phone = parsed.phone
            candidate.skills = parsed.skills
            candidate.experience_years = parsed.total_years_exp
            candidate.experience = [e.model_dump() for e in parsed.experience]
            candidate.education = [e.model_dump() for e in parsed.education]

            await embedding_service.embed_and_store_candidate(session, candidate, raw_text)

            candidate.parsing_status = ParsingStatus.COMPLETED
            await session.commit()
        except Exception as exc:
            logger.exception("Resume processing failed for candidate %s", candidate_id)
            await session.rollback()
            # Re-fetch: rollback() expires the in-memory object, and this is an
            # async session so lazy-reloading a stale attribute would break.
            failed_candidate = await session.get(Candidate, candidate_id)
            if failed_candidate is not None:
                failed_candidate.parsing_status = ParsingStatus.FAILED
                failed_candidate.parsing_error = str(exc)[:1000]
                await session.commit()
