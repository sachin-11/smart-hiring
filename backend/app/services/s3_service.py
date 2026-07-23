import asyncio
import logging
import uuid

import boto3
from botocore.exceptions import ClientError

from app.core.config import settings

logger = logging.getLogger(__name__)

_s3_client = boto3.client(
    "s3",
    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    region_name=settings.AWS_REGION,
)

_CONTENT_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def _build_key(candidate_id: uuid.UUID, filename: str) -> str:
    safe_name = filename.replace("/", "_").replace("\\", "_")
    return f"resumes/{candidate_id}/{safe_name}"


def _build_interview_key(session_id: uuid.UUID, filename: str) -> str:
    safe_name = filename.replace("/", "_").replace("\\", "_")
    return f"interviews/{session_id}/{safe_name}"


def _build_report_key(report_id: uuid.UUID) -> str:
    return f"reports/{report_id}/scorecard.pdf"


def _build_drift_report_key(report_id: uuid.UUID) -> str:
    return f"mlops/drift-reports/{report_id}.json"


def _put_object_sync(key: str, data: bytes, content_type: str) -> None:
    _s3_client.put_object(
        Bucket=settings.AWS_S3_BUCKET,
        Key=key,
        Body=data,
        ContentType=content_type,
    )


async def upload_resume_file(candidate_id: uuid.UUID, filename: str, data: bytes) -> tuple[str, str]:
    """Uploads resume bytes to S3. Returns (s3_key, object_url)."""
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    content_type = _CONTENT_TYPES.get(ext, "application/octet-stream")
    key = _build_key(candidate_id, filename)

    try:
        # boto3 is sync; run it off the event loop so we don't block other requests.
        await asyncio.to_thread(_put_object_sync, key, data, content_type)
    except ClientError:
        logger.exception("Failed to upload resume to S3 (key=%s)", key)
        raise

    object_url = f"https://{settings.AWS_S3_BUCKET}.s3.{settings.AWS_REGION}.amazonaws.com/{key}"
    return key, object_url


async def upload_interview_audio(session_id: uuid.UUID, filename: str, data: bytes, content_type: str) -> tuple[str, str]:
    """Uploads a candidate answer recording or a generated TTS clip to S3. Returns (s3_key, object_url)."""
    key = _build_interview_key(session_id, filename)
    try:
        await asyncio.to_thread(_put_object_sync, key, data, content_type)
    except ClientError:
        logger.exception("Failed to upload interview audio to S3 (key=%s)", key)
        raise

    object_url = f"https://{settings.AWS_S3_BUCKET}.s3.{settings.AWS_REGION}.amazonaws.com/{key}"
    return key, object_url


async def upload_report_pdf(report_id: uuid.UUID, data: bytes) -> tuple[str, str]:
    """Uploads a generated candidate scorecard PDF to S3. Returns (s3_key, object_url)."""
    key = _build_report_key(report_id)
    try:
        await asyncio.to_thread(_put_object_sync, key, data, "application/pdf")
    except ClientError:
        logger.exception("Failed to upload report PDF to S3 (key=%s)", key)
        raise

    object_url = f"https://{settings.AWS_S3_BUCKET}.s3.{settings.AWS_REGION}.amazonaws.com/{key}"
    return key, object_url


async def upload_drift_report(report_id: uuid.UUID, data: bytes) -> tuple[str, str]:
    """Uploads a JSON embedding-drift report to S3. Returns (s3_key, object_url)."""
    key = _build_drift_report_key(report_id)
    try:
        await asyncio.to_thread(_put_object_sync, key, data, "application/json")
    except ClientError:
        logger.exception("Failed to upload drift report to S3 (key=%s)", key)
        raise

    object_url = f"https://{settings.AWS_S3_BUCKET}.s3.{settings.AWS_REGION}.amazonaws.com/{key}"
    return key, object_url


def generate_presigned_url(key: str, expires_in: int = 3600) -> str:
    return _s3_client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.AWS_S3_BUCKET, "Key": key},
        ExpiresIn=expires_in,
    )
