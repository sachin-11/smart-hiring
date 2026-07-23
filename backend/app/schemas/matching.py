import uuid

from pydantic import BaseModel, Field


class MatchRequest(BaseModel):
    jd_id: uuid.UUID
    top_k: int = Field(default=10, ge=1, le=50)


class MatchResult(BaseModel):
    candidate_id: uuid.UUID
    name: str | None = None
    match_score: float = Field(description="0-100 relevance score from cross-encoder reranking")
    skill_overlap: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    explanation: str = ""


class MatchResponse(BaseModel):
    jd_id: uuid.UUID
    results: list[MatchResult]
