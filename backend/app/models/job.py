import enum
import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import ARRAY, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base, db_enum
from app.models.candidate import EMBEDDING_DIM


class JobStatus(str, enum.Enum):
    DRAFT = "draft"
    OPEN = "open"
    PAUSED = "paused"
    CLOSED = "closed"


class EmploymentType(str, enum.Enum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    INTERNSHIP = "internship"


class ApplicationStatus(str, enum.Enum):
    APPLIED = "applied"
    SHORTLISTED = "shortlisted"
    INTERVIEWING = "interviewing"
    OFFERED = "offered"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class SeniorityLevel(str, enum.Enum):
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    LEAD = "lead"
    PRINCIPAL = "principal"


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    department: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    employment_type: Mapped[EmploymentType] = mapped_column(
        db_enum(EmploymentType, name="employment_type"),
        default=EmploymentType.FULL_TIME,
        nullable=False,
    )

    min_experience: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_experience: Mapped[float | None] = mapped_column(Float, nullable=True)
    salary_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    salary_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    required_skills: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    nice_to_have_skills: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    responsibilities: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    seniority_level: Mapped[SeniorityLevel | None] = mapped_column(
        db_enum(SeniorityLevel, name="seniority_level"), nullable=True
    )

    description_embedding: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_DIM), nullable=True
    )

    status: Mapped[JobStatus] = mapped_column(
        db_enum(JobStatus, name="job_status"), default=JobStatus.DRAFT, nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    applications: Mapped[list["Application"]] = relationship(
        "Application", back_populates="job", cascade="all, delete-orphan"
    )
    interviews: Mapped[list["Interview"]] = relationship(
        "Interview", back_populates="job", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Job id={self.id} title={self.title!r}>"


class Application(Base):
    """Join between a Candidate and a Job, tracking pipeline status and match score."""

    __tablename__ = "applications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )

    status: Mapped[ApplicationStatus] = mapped_column(
        db_enum(ApplicationStatus, name="application_status"),
        default=ApplicationStatus.APPLIED,
        nullable=False,
    )
    match_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    candidate: Mapped["Candidate"] = relationship("Candidate", back_populates="applications")
    job: Mapped["Job"] = relationship("Job", back_populates="applications")

    def __repr__(self) -> str:
        return f"<Application candidate_id={self.candidate_id} job_id={self.job_id}>"
