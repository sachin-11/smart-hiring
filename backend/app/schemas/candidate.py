import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.candidate import CandidateStatus


class CandidateListItem(BaseModel):
    id: uuid.UUID
    full_name: str | None = None
    email: str | None = None
    status: CandidateStatus
    skills: list[str] = Field(default_factory=list)
    applied_job_title: str | None = None
    applied_job_id: uuid.UUID | None = None
    match_score: float | None = None
    created_at: datetime


class CandidateListResponse(BaseModel):
    candidates: list[CandidateListItem]
    total: int


class BulkShortlistRequest(BaseModel):
    candidate_ids: list[uuid.UUID] = Field(min_length=1)


class BulkEmailRequest(BaseModel):
    candidate_ids: list[uuid.UUID] = Field(min_length=1)
    job_id: uuid.UUID
    message: str | None = None


class BulkActionResponse(BaseModel):
    affected: int


class CandidateDeleteResponse(BaseModel):
    candidate_id: uuid.UUID
    interviews_deleted: int
    reports_deleted: int
    s3_objects_deleted: int
