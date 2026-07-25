import enum
import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import ARRAY, JSON, DateTime, Float, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base, db_enum

# OpenAI text-embedding-3-small dimension
EMBEDDING_DIM = 1536


class CandidateStatus(str, enum.Enum):
    NEW = "new"
    SCREENING = "screening"
    INTERVIEWING = "interviewing"
    OFFERED = "offered"
    HIRED = "hired"
    REJECTED = "rejected"


class ParsingStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Candidate(Base):
    __tablename__ = "candidates"
    __table_args__ = (
        # Approximate nearest-neighbor index for cosine similarity search
        # (matching_service.py's .cosine_distance() calls) — without this,
        # every hybrid-search query does a full sequential scan over embeddings.
        Index(
            "ix_candidates_resume_embedding_ivfflat",
            "resume_embedding",
            postgresql_using="ivfflat",
            postgresql_with={"lists": "100"},
            postgresql_ops={"resume_embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Nullable because a candidate row is created at upload time, before the
    # resume has been parsed and these fields are actually known.
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)

    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    s3_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    resume_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    resume_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    skills: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    experience: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    education: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    experience_years: Mapped[float | None] = mapped_column(Float, nullable=True)

    resume_embedding: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_DIM), nullable=True
    )

    status: Mapped[CandidateStatus] = mapped_column(
        db_enum(CandidateStatus, name="candidate_status"),
        default=CandidateStatus.NEW,
        nullable=False,
    )
    parsing_status: Mapped[ParsingStatus] = mapped_column(
        db_enum(ParsingStatus, name="parsing_status"),
        default=ParsingStatus.PENDING,
        nullable=False,
    )
    parsing_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    applications: Mapped[list["Application"]] = relationship(
        "Application", back_populates="candidate", cascade="all, delete-orphan"
    )
    interviews: Mapped[list["Interview"]] = relationship(
        "Interview", back_populates="candidate", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Candidate id={self.id} email={self.email}>"
