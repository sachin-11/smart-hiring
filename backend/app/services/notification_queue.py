"""Redis-backed notification queue (cache-aside's cousin: queue-aside).

There's no dedicated worker process/deployment in this stack (no Celery, no separate
container) — so `drain_queue()` is called as a FastAPI BackgroundTask right after
enqueueing, which processes whatever's currently queued in the same process. The
queue itself (a Redis list, LPUSH/BRPOP) is real and would work unchanged with a
genuine standalone worker consuming it; see MODULE_8_SETUP.md.
"""

import json
import logging
from typing import Any

from app.core.redis_client import get_redis_client
from app.services import email_service, slack_service

logger = logging.getLogger(__name__)

QUEUE_KEY = "notifications:queue"


async def enqueue(payload: dict[str, Any]) -> None:
    redis = get_redis_client()
    try:
        await redis.lpush(QUEUE_KEY, json.dumps(payload))
    finally:
        await redis.aclose()


async def _dispatch(payload: dict[str, Any]) -> None:
    notification_type = payload.get("type")
    if notification_type == "shortlist_email":
        await email_service.send_shortlist_email(
            payload["to_email"], payload.get("candidate_name"), payload.get("job_title"), payload.get("message")
        )
    elif notification_type == "slack":
        await slack_service.send_slack_alert(payload["text"])
    else:
        logger.error("Unknown notification type in queue: %r", notification_type)


async def drain_queue() -> int:
    """Pops and processes every item currently on the queue (non-blocking).
    Best-effort per item: one failure doesn't stop the rest of the batch."""
    redis = get_redis_client()
    processed = 0
    try:
        while True:
            raw = await redis.rpop(QUEUE_KEY)
            if raw is None:
                break
            payload = json.loads(raw)
            try:
                await _dispatch(payload)
            except Exception:
                logger.exception("Failed to process queued notification: %r", payload)
            processed += 1
    finally:
        await redis.aclose()
    return processed
