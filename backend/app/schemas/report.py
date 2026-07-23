import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

Recommendation = Literal["Strongly Hire", "Hire", "Hold", "Reject"]
ProficiencyLevel = Literal["Beginner", "Intermediate", "Advanced", "Expert"]


class TechnicalAssessment(BaseModel):
    score: float = Field(ge=0, le=10, description="Technical competence, 0-10")
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    comments: str


class CommunicationAssessment(BaseModel):
    score: float = Field(ge=0, le=10, description="Communication quality, 0-10")
    clarity: str = Field(description="How clear and well-structured the candidate's answers were")
    articulation: str = Field(description="How well the candidate expressed complex ideas")
    examples: list[str] = Field(default_factory=list, description="Short quoted/paraphrased examples from the transcript")


class CultureFit(BaseModel):
    score: float = Field(ge=0, le=10, description="Culture fit signal, 0-10")
    comments: str


class SkillBreakdownItem(BaseModel):
    skill: str
    proficiency_level: ProficiencyLevel
    evidence: str = Field(description="What in the resume/interview supports this level")


class InterviewHighlights(BaseModel):
    best_answer: str = Field(description="Summary of the candidate's strongest moment in the interview")
    concern_answer: str = Field(description="Summary of the candidate's weakest or most concerning moment")


class ReportSchema(BaseModel):
    """Structured output the report_agent LLM call must produce."""

    overall_score: float = Field(ge=0, le=10, description="Weighted overall score, 0-10")
    recommendation: Recommendation
    technical_assessment: TechnicalAssessment
    communication_assessment: CommunicationAssessment
    culture_fit: CultureFit
    skill_breakdown: list[SkillBreakdownItem] = Field(default_factory=list)
    interview_highlights: InterviewHighlights
    suggested_next_steps: str
    red_flags: list[str] = Field(default_factory=list)


class ReportGenerateRequest(BaseModel):
    session_id: uuid.UUID = Field(description="Interview id (Module 5 session_id) to build the report from")


class ReportDetailResponse(BaseModel):
    report_id: uuid.UUID
    interview_id: uuid.UUID
    candidate_id: uuid.UUID
    job_id: uuid.UUID
    candidate_name: str | None = None
    job_title: str | None = None
    created_at: datetime
    report: ReportSchema


class ReportPdfResponse(BaseModel):
    report_id: uuid.UUID
    pdf_url: str


class ReportShareRequest(BaseModel):
    to_email: EmailStr
    message: str | None = Field(default=None, description="Optional note to include in the email body")


class ReportShareResponse(BaseModel):
    sent: bool
    detail: str
