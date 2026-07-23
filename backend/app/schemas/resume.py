import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.candidate import ParsingStatus


class ExperienceEntry(BaseModel):
    company: str = Field(description="Employer / company name")
    title: str = Field(description="Job title or role")
    start_date: str | None = Field(default=None, description="Start date as written, e.g. 'Jan 2020'")
    end_date: str | None = Field(default=None, description="End date as written, or null if current")
    is_current: bool = Field(default=False, description="Whether this is the candidate's current role")
    description: str | None = Field(default=None, description="Brief summary of responsibilities/achievements")


class EducationEntry(BaseModel):
    institution: str = Field(description="School or university name")
    degree: str | None = Field(default=None, description="Degree obtained, e.g. 'B.Sc.', 'M.Tech'")
    field_of_study: str | None = Field(default=None, description="Major / field of study")
    start_year: int | None = Field(default=None)
    end_year: int | None = Field(default=None)


class ResumeData(BaseModel):
    """Structured output schema the LLM populates from raw resume text."""

    name: str | None = Field(default=None, description="Candidate's full name")
    email: str | None = Field(default=None, description="Candidate's email address")
    phone: str | None = Field(default=None, description="Candidate's phone number")
    skills: list[str] = Field(default_factory=list, description="Flat list of technical/professional skills")
    experience: list[ExperienceEntry] = Field(default_factory=list)
    education: list[EducationEntry] = Field(default_factory=list)
    total_years_exp: float | None = Field(
        default=None,
        description="Total years of professional experience, estimated from the experience entries",
    )


class ResumeUploadResponse(BaseModel):
    candidate_id: uuid.UUID
    status: ParsingStatus


class ResumeStatusResponse(BaseModel):
    candidate_id: uuid.UUID
    status: ParsingStatus
    error: str | None = None


class ResumeDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: ParsingStatus = Field(validation_alias="parsing_status")
    error: str | None = Field(default=None, validation_alias="parsing_error")
    original_filename: str | None = None
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    skills: list[str] | None = None
    experience: list[ExperienceEntry] | None = None
    education: list[EducationEntry] | None = None
    total_years_exp: float | None = Field(default=None, validation_alias="experience_years")
    resume_url: str | None = None
