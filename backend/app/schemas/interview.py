import uuid

from pydantic import BaseModel, Field

from app.models.interview import InterviewStatus


class InterviewQuestion(BaseModel):
    question: str
    category: str = Field(description="One of: technical, behavioral, situational, culture")
    rationale: str = Field(description="Chain-of-thought: why this question fits this candidate/role")


class InterviewQuestionSet(BaseModel):
    questions: list[InterviewQuestion] = Field(default_factory=list)


class AnswerQuality(BaseModel):
    """Structured output for scoring a candidate's answer."""

    score: int = Field(ge=1, le=5, description="1=weak/evasive, 5=excellent, specific, well-reasoned")
    feedback: str = Field(description="One-sentence rationale for the score")


class AnswerJudgment(BaseModel):
    """Structured output for an independent LLM-as-judge re-scoring of an
    already-scored answer, blind to the original score."""

    score: int = Field(ge=1, le=5, description="Independent 1-5 quality score for this answer")
    reasoning: str = Field(description="One-sentence justification for the score")


class QAExchange(BaseModel):
    question: str
    category: str
    is_follow_up: bool
    answer: str | None = None
    score: int | None = None
    feedback: str | None = None


class InterviewStartRequest(BaseModel):
    candidate_id: uuid.UUID
    job_id: uuid.UUID


class InterviewStartResponse(BaseModel):
    session_id: uuid.UUID
    question: str
    category: str
    question_index: int
    total_questions: int
    audio_url: str | None = None


class InterviewAnswerRequest(BaseModel):
    session_id: uuid.UUID
    answer_text: str = Field(min_length=1)


class InterviewAnswerResponse(BaseModel):
    session_id: uuid.UUID
    score: int | None = None
    feedback: str | None = None
    is_follow_up: bool
    complete: bool
    question: str | None = None
    category: str | None = None
    question_index: int
    total_questions: int
    audio_url: str | None = None


class InterviewTranscriptResponse(BaseModel):
    session_id: uuid.UUID
    candidate_id: uuid.UUID
    job_id: uuid.UUID
    status: InterviewStatus
    exchanges: list[QAExchange]
    question_index: int
    total_questions: int
    average_score: float | None = None
