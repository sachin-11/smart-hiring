import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class SlackNotConfiguredError(RuntimeError):
    pass


async def send_slack_alert(text: str) -> None:
    if not settings.SLACK_WEBHOOK_URL:
        raise SlackNotConfiguredError("SLACK_WEBHOOK_URL is not configured")

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(settings.SLACK_WEBHOOK_URL, json={"text": text})
            response.raise_for_status()
    except httpx.HTTPError:
        logger.exception("Failed to send Slack alert")
        raise
