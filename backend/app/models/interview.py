import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base, db_enum


class InterviewType(str, enum.Enum):
    SCREENING = "screening"
    TECHNICAL = "technical"
    BEHAVIORAL = "behavioral"
    FINAL = "final"


class InterviewStatus(str, enum.Enum):
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


class Interview(Base):
    __tablename__ = "interviews"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )

    interview_type: Mapped[InterviewType] = mapped_column(
        db_enum(InterviewType, name="interview_type"),
        default=InterviewType.SCREENING,
        nullable=False,
    )
    status: Mapped[InterviewStatus] = mapped_column(
        db_enum(InterviewStatus, name="interview_status"),
        default=InterviewStatus.SCHEDULED,
        nullable=False,
    )

    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    recording_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    ai_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    ai_feedback: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    candidate: Mapped["Candidate"] = relationship("Candidate", back_populates="interviews")
    job: Mapped["Job"] = relationship("Job", back_populates="interviews")

    def __repr__(self) -> str:
        return f"<Interview id={self.id} candidate_id={self.candidate_id} job_id={self.job_id}>"
