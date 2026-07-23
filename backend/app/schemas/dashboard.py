import uuid
from datetime import datetime

from pydantic import BaseModel


class DashboardStats(BaseModel):
    total_candidates: int
    active_jds: int
    avg_match_score: float | None
    interviews_scheduled: int


class ActivityItem(BaseModel):
    id: uuid.UUID
    type: str
    description: str
    timestamp: datetime


class DashboardActivityResponse(BaseModel):
    items: list[ActivityItem]
