import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_recruiter
from app.models.candidate import Candidate
from app.models.job import Job
from app.models.recruiter import Recruiter
from app.schemas.notifications import NotifyResponse, ShortlistNotifyRequest, SlackNotifyRequest
from app.services import notification_queue

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notify", tags=["notifications"])


@router.post("/shortlist", response_model=NotifyResponse)
async def notify_shortlist(
    payload: ShortlistNotifyRequest,
    db: AsyncSession = Depends(get_db),
    _recruiter: Recruiter = Depends(get_current_recruiter),
) -> NotifyResponse:
    candidate = await db.get(Candidate, payload.candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    if not candidate.email:
        raise HTTPException(status_code=400, detail="Candidate has no email on file")
    job = await db.get(Job, payload.job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    await notification_queue.enqueue(
        {
            "type": "shortlist_email",
            "to_email": candidate.email,
            "candidate_name": candidate.full_name,
            "job_title": job.title,
            "message": payload.message,
        }
    )
    processed = await notification_queue.drain_queue()
    return NotifyResponse(queued=True, processed=processed)


@router.post("/slack", response_model=NotifyResponse)
async def notify_slack(
    payload: SlackNotifyRequest, _recruiter: Recruiter = Depends(get_current_recruiter)
) -> NotifyResponse:
    await notification_queue.enqueue({"type": "slack", "text": payload.text})
    processed = await notification_queue.drain_queue()
    return NotifyResponse(queued=True, processed=processed)
