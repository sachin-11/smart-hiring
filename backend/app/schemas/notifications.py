import uuid

from pydantic import BaseModel, Field


class ShortlistNotifyRequest(BaseModel):
    candidate_id: uuid.UUID
    job_id: uuid.UUID
    message: str | None = None


class SlackNotifyRequest(BaseModel):
    text: str = Field(min_length=1)


class NotifyResponse(BaseModel):
    queued: bool
    processed: int
