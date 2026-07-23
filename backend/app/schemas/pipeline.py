import uuid

from pydantic import BaseModel, Field


class PipelineRunRequest(BaseModel):
    candidate_id: uuid.UUID
    job_id: uuid.UUID


class InterviewQuestion(BaseModel):
    question: str
    category: str = Field(description="e.g. 'technical', 'behavioral', 'system_design'")
    rationale: str | None = Field(default=None, description="Why this question is relevant")


class InterviewQuestionSet(BaseModel):
    questions: list[InterviewQuestion] = Field(default_factory=list)


class CandidateReport(BaseModel):
    summary: str
    strengths: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    recommendation: str = Field(description="e.g. 'proceed to interview', 'reject', 'consider for other roles'")
