import enum
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import Enum, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


def db_enum(enum_cls: type[enum.Enum], name: str) -> Enum:
    """SQLAlchemy Enum bound to a str Enum's `.value`s instead of member names.

    Without `values_callable`, SQLAlchemy sends the Python member *name*
    (e.g. "PENDING") to Postgres, but our enum types/migrations use the
    lowercase `.value` (e.g. "pending") — mismatched writes fail at insert time.
    """
    return Enum(enum_cls, name=name, values_callable=lambda obj: [e.value for e in obj])


engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_pre_ping=True,
    future=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def init_db() -> None:
    """Enable the pgvector extension and create all tables."""
    try:
        async with engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database initialized and pgvector extension ensured.")
    except Exception:
        logger.exception("Failed to initialize database")
        raise


async def close_db() -> None:
    await engine.dispose()
    logger.info("Database engine disposed.")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async DB session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """Context manager for use outside of FastAPI request handlers (e.g. agents, scripts)."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
