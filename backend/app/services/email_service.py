import asyncio
import logging

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

from app.core.config import settings

logger = logging.getLogger(__name__)


class EmailNotConfiguredError(RuntimeError):
    pass


def _send_sync(to_email: str, subject: str, html_content: str) -> None:
    client = SendGridAPIClient(settings.SENDGRID_API_KEY)
    mail = Mail(
        from_email=settings.SENDGRID_FROM_EMAIL,
        to_emails=to_email,
        subject=subject,
        html_content=html_content,
    )
    response = client.send(mail)
    if response.status_code >= 300:
        raise RuntimeError(f"SendGrid returned status {response.status_code}: {response.body}")


def _require_configured() -> None:
    if not settings.SENDGRID_API_KEY:
        raise EmailNotConfiguredError("SENDGRID_API_KEY is not configured")


async def send_report_share_email(
    to_email: str, candidate_name: str | None, job_title: str | None, pdf_url: str, message: str | None
) -> None:
    _require_configured()

    subject = f"Candidate Scorecard: {candidate_name or 'Candidate'} — {job_title or 'Role'}"
    note_html = f"<p>{message}</p>" if message else ""
    html_content = (
        f"<p>Here is the candidate scorecard for <b>{candidate_name or 'the candidate'}</b> "
        f"({job_title or 'role'}).</p>"
        f"{note_html}"
        f'<p><a href="{pdf_url}">Download the PDF report</a></p>'
        f"<p style='color:#64748b;font-size:12px'>This link expires; regenerate it from the report page if needed.</p>"
    )

    try:
        # sendgrid's client is sync; run it off the event loop like the boto3 calls elsewhere.
        await asyncio.to_thread(_send_sync, to_email, subject, html_content)
    except Exception:
        logger.exception("Failed to send report share email to %s", to_email)
        raise


async def send_password_reset_email(to_email: str, reset_url: str) -> None:
    _require_configured()

    subject = "Reset your Smart Hiring password"
    html_content = (
        f"<p>We received a request to reset your Smart Hiring password.</p>"
        f'<p><a href="{reset_url}">Click here to choose a new password</a></p>'
        f"<p style='color:#64748b;font-size:12px'>This link expires in 1 hour. "
        "If you didn't request this, you can safely ignore this email.</p>"
    )

    try:
        await asyncio.to_thread(_send_sync, to_email, subject, html_content)
    except Exception:
        logger.exception("Failed to send password reset email to %s", to_email)
        raise


async def send_shortlist_email(to_email: str, candidate_name: str | None, job_title: str | None, message: str | None) -> None:
    _require_configured()

    subject = f"You've been shortlisted for {job_title or 'a role'}"
    note_html = f"<p>{message}</p>" if message else ""
    html_content = (
        f"<p>Hi {candidate_name or 'there'},</p>"
        f"<p>Good news — you've been shortlisted for the <b>{job_title or 'role'}</b> position. "
        "Our recruiting team will follow up shortly with next steps.</p>"
        f"{note_html}"
    )

    try:
        await asyncio.to_thread(_send_sync, to_email, subject, html_content)
    except Exception:
        logger.exception("Failed to send shortlist email to %s", to_email)
        raise
