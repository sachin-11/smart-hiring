import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.job import EmploymentType, JobStatus, SeniorityLevel


class JDAnalysis(BaseModel):
    """Structured output schema the LLM populates from raw job description text."""

    title: str | None = Field(default=None, description="Job title, if identifiable from the text")
    required_skills: list[str] = Field(default_factory=list, description="Must-have skills")
    nice_to_have: list[str] = Field(default_factory=list, description="Preferred but not required skills")
    min_experience: float | None = Field(default=None, description="Minimum years of experience required")
    responsibilities: list[str] = Field(default_factory=list, description="Key responsibilities/duties")
    seniority_level: SeniorityLevel | None = Field(
        default=None, description="Seniority level implied by the JD"
    )


class JobCreateRequest(BaseModel):
    title: str
    description: str
    required_skills: list[str] = Field(default_factory=list)
    min_experience: float | None = None
    max_experience: float | None = None
    department: str | None = None
    location: str | None = None
    employment_type: EmploymentType = EmploymentType.FULL_TIME


class JobDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str
    department: str | None = None
    location: str | None = None
    employment_type: EmploymentType
    min_experience: float | None = None
    max_experience: float | None = None
    required_skills: list[str] | None = None
    nice_to_have_skills: list[str] | None = None
    responsibilities: list[str] | None = None
    seniority_level: SeniorityLevel | None = None
    status: JobStatus
    created_at: datetime


class JobListItem(BaseModel):
    id: uuid.UUID
    title: str
    department: str | None = None
    location: str | None = None
    status: JobStatus
    applicant_count: int
    top_match_score: float | None = None
    created_at: datetime


class JobListResponse(BaseModel):
    jobs: list[JobListItem]
    total: int
