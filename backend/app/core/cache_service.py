import json
import logging
import uuid
from typing import Any

from app.core.redis_client import get_redis_client

logger = logging.getLogger(__name__)

MATCH_RESULTS_TTL_SECONDS = 60 * 60  # 1 hour
JD_EMBEDDING_TTL_SECONDS = 24 * 60 * 60  # 24 hours

_MATCH_RESULTS_PREFIX = "cache:match_results"
_JD_EMBEDDING_PREFIX = "cache:jd_embedding"


async def get_cached_match_results(job_id: uuid.UUID, top_k: int) -> list[dict] | None:
    """Cache-aside read: returns None on a miss (including a Redis outage), so
    the caller always has a safe fallback of recomputing from the source of truth."""
    redis = get_redis_client()
    try:
        raw = await redis.get(f"{_MATCH_RESULTS_PREFIX}:{job_id}:{top_k}")
        return json.loads(raw) if raw else None
    except Exception:
        logger.warning("Match-results cache read failed for job=%s", job_id, exc_info=True)
        return None
    finally:
        await redis.aclose()


async def set_cached_match_results(job_id: uuid.UUID, top_k: int, results: list[dict]) -> None:
    redis = get_redis_client()
    try:
        await redis.set(
            f"{_MATCH_RESULTS_PREFIX}:{job_id}:{top_k}", json.dumps(results), ex=MATCH_RESULTS_TTL_SECONDS
        )
    except Exception:
        logger.warning("Match-results cache write failed for job=%s", job_id, exc_info=True)
    finally:
        await redis.aclose()


async def invalidate_match_results(job_id: uuid.UUID) -> None:
    """Call this whenever the job or candidate pool changes in a way that could
    change match results (e.g. a new resume finishes parsing)."""
    redis = get_redis_client()
    try:
        keys = [key async for key in redis.scan_iter(match=f"{_MATCH_RESULTS_PREFIX}:{job_id}:*")]
        if keys:
            await redis.delete(*keys)
    except Exception:
        logger.warning("Match-results cache invalidation failed for job=%s", job_id, exc_info=True)
    finally:
        await redis.aclose()


async def get_cached_jd_embedding(job_id: uuid.UUID) -> list[float] | None:
    redis = get_redis_client()
    try:
        raw = await redis.get(f"{_JD_EMBEDDING_PREFIX}:{job_id}")
        return json.loads(raw) if raw else None
    except Exception:
        logger.warning("JD-embedding cache read failed for job=%s", job_id, exc_info=True)
        return None
    finally:
        await redis.aclose()


async def set_cached_jd_embedding(job_id: uuid.UUID, embedding: list[float]) -> None:
    redis = get_redis_client()
    try:
        await redis.set(f"{_JD_EMBEDDING_PREFIX}:{job_id}", json.dumps(embedding), ex=JD_EMBEDDING_TTL_SECONDS)
    except Exception:
        logger.warning("JD-embedding cache write failed for job=%s", job_id, exc_info=True)
    finally:
        await redis.aclose()


async def get_or_set_jd_embedding(job_id: uuid.UUID, compute: Any) -> list[float]:
    """Cache-aside: check Redis first, fall back to `compute()` (the job's
    already-persisted `description_embedding` column) on a miss, and populate
    the cache for next time. `compute` is an async callable taking no args."""
    cached = await get_cached_jd_embedding(job_id)
    if cached is not None:
        return cached

    embedding = await compute()
    await set_cached_jd_embedding(job_id, embedding)
    return embedding
