import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings

logger = logging.getLogger(__name__)

if not settings.JWT_SECRET_KEY:
    logger.warning(
        "JWT_SECRET_KEY is not configured — generating a random one for this process. "
        "All existing tokens will be invalidated on every restart. Set JWT_SECRET_KEY "
        "in .env for a stable secret."
    )
_SECRET_KEY = settings.JWT_SECRET_KEY or secrets.token_urlsafe(32)

ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"
INTERVIEW_ACCESS_TOKEN_TYPE = "interview_access"


class TokenError(Exception):
    pass


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


def _create_token(recruiter_id: uuid.UUID, token_type: str, ttl: timedelta, jti: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(recruiter_id),
        "type": token_type,
        "jti": jti,
        "iat": now,
        "exp": now + ttl,
    }
    return jwt.encode(payload, _SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(recruiter_id: uuid.UUID) -> str:
    return _create_token(
        recruiter_id,
        ACCESS_TOKEN_TYPE,
        timedelta(minutes=settings.JWT_ACCESS_TOKEN_TTL_MINUTES),
        jti=secrets.token_hex(8),
    )


def create_refresh_token(recruiter_id: uuid.UUID) -> tuple[str, str]:
    """Returns (token, jti) — the caller stores jti in Redis so refresh tokens can be
    rotated/revoked without needing a DB round-trip on every refresh."""
    jti = secrets.token_hex(16)
    token = _create_token(recruiter_id, REFRESH_TOKEN_TYPE, timedelta(days=settings.JWT_REFRESH_TOKEN_TTL_DAYS), jti)
    return token, jti


def create_interview_access_token(session_id: uuid.UUID) -> str:
    """A candidate-facing magic-link token scoped to exactly one interview
    session — lets a candidate open and take their interview without a
    recruiter account. Stateless (no Redis lookup needed): validity is just
    "well-formed, unexpired, and its `sub` matches the session_id in the URL"."""
    return _create_token(
        session_id,
        INTERVIEW_ACCESS_TOKEN_TYPE,
        timedelta(hours=settings.INTERVIEW_ACCESS_TOKEN_TTL_HOURS),
        jti=secrets.token_hex(8),
    )


def decode_token(token: str, expected_type: str) -> dict:
    try:
        payload = jwt.decode(token, _SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError as exc:
        raise TokenError(f"Invalid or expired token: {exc}") from exc

    if payload.get("type") != expected_type:
        raise TokenError(f"Expected a {expected_type} token, got {payload.get('type')}")
    return payload
