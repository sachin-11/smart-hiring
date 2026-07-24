import logging
import secrets
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.config import settings
from app.core.database import get_db
from app.core.rate_limit import limiter
from app.core.redis_client import get_redis_client
from app.models.recruiter import Recruiter
from app.schemas.auth import (
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    RecruiterResponse,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
)
from app.services import email_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

_REFRESH_SESSION_PREFIX = "auth:refresh"
_RESET_TOKEN_PREFIX = "auth:reset"
_RESET_TOKEN_TTL = timedelta(hours=1)


def _refresh_key(jti: str) -> str:
    return f"{_REFRESH_SESSION_PREFIX}:{jti}"


async def _store_refresh_session(jti: str, recruiter_id: uuid.UUID) -> None:
    redis = get_redis_client()
    try:
        await redis.set(
            _refresh_key(jti), str(recruiter_id), ex=timedelta(days=settings.JWT_REFRESH_TOKEN_TTL_DAYS)
        )
    finally:
        await redis.aclose()


async def _consume_refresh_session(jti: str) -> str | None:
    """Single-use refresh tokens: atomically pop the session so a stolen/replayed
    refresh token can't be used twice (classic refresh-token rotation)."""
    redis = get_redis_client()
    try:
        pipe = redis.pipeline()
        pipe.get(_refresh_key(jti))
        pipe.delete(_refresh_key(jti))
        recruiter_id, _ = await pipe.execute()
        return recruiter_id
    finally:
        await redis.aclose()


async def _issue_tokens(recruiter: Recruiter) -> TokenResponse:
    access_token = security.create_access_token(recruiter.id)
    refresh_token, jti = security.create_refresh_token(recruiter.id)
    await _store_refresh_session(jti, recruiter.id)
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        recruiter=RecruiterResponse(id=recruiter.id, email=recruiter.email, full_name=recruiter.full_name),
    )


@router.post("/register", response_model=TokenResponse, status_code=201)
@limiter.limit(settings.RATE_LIMIT_REGISTER)
async def register(request: Request, payload: RegisterRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    existing = (await db.execute(select(Recruiter).where(Recruiter.email == payload.email))).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    recruiter = Recruiter(
        id=uuid.uuid4(),
        email=payload.email,
        hashed_password=security.hash_password(payload.password),
        full_name=payload.full_name,
    )
    db.add(recruiter)
    await db.commit()
    await db.refresh(recruiter)

    return await _issue_tokens(recruiter)


@router.post("/login", response_model=TokenResponse)
@limiter.limit(settings.RATE_LIMIT_LOGIN)
async def login(request: Request, payload: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    recruiter = (await db.execute(select(Recruiter).where(Recruiter.email == payload.email))).scalar_one_or_none()
    if recruiter is None or not security.verify_password(payload.password, recruiter.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    if not recruiter.is_active:
        raise HTTPException(status_code=403, detail="This account has been deactivated")

    return await _issue_tokens(recruiter)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    try:
        claims = security.decode_token(payload.refresh_token, expected_type=security.REFRESH_TOKEN_TYPE)
    except security.TokenError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    stored_recruiter_id = await _consume_refresh_session(claims["jti"])
    if stored_recruiter_id is None:
        # Missing/already-used jti: either expired, or a token replay — reject either way.
        raise HTTPException(status_code=401, detail="Refresh token has expired or already been used")

    recruiter = await db.get(Recruiter, uuid.UUID(claims["sub"]))
    if recruiter is None or not recruiter.is_active:
        raise HTTPException(status_code=401, detail="Recruiter account no longer exists or is inactive")

    return await _issue_tokens(recruiter)


def _reset_key(token: str) -> str:
    return f"{_RESET_TOKEN_PREFIX}:{token}"


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
@limiter.limit(settings.RATE_LIMIT_FORGOT_PASSWORD)
async def forgot_password(
    request: Request, payload: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)
) -> ForgotPasswordResponse:
    # Always return the same response whether or not the email exists — a
    # different response would let an attacker enumerate registered emails.
    generic_response = ForgotPasswordResponse(
        detail="If an account exists for that email, a password reset link has been sent."
    )

    recruiter = (await db.execute(select(Recruiter).where(Recruiter.email == payload.email))).scalar_one_or_none()
    if recruiter is None or not recruiter.is_active:
        return generic_response

    token = secrets.token_urlsafe(32)
    redis = get_redis_client()
    try:
        await redis.set(_reset_key(token), str(recruiter.id), ex=_RESET_TOKEN_TTL)
    finally:
        await redis.aclose()

    reset_url = f"{settings.FRONTEND_URL}/reset-password?token={token}"
    try:
        await email_service.send_password_reset_email(recruiter.email, reset_url)
    except email_service.EmailNotConfiguredError:
        logger.warning("Password reset requested for %s but SENDGRID_API_KEY is not configured", recruiter.email)
    except Exception:
        logger.exception("Failed to send password reset email to %s", recruiter.email)

    return generic_response


@router.post("/reset-password", response_model=ForgotPasswordResponse)
async def reset_password(payload: ResetPasswordRequest, db: AsyncSession = Depends(get_db)) -> ForgotPasswordResponse:
    redis = get_redis_client()
    try:
        # Single-use, same pattern as refresh-token rotation: pop atomically so a
        # replayed reset link can't be used twice.
        pipe = redis.pipeline()
        pipe.get(_reset_key(payload.token))
        pipe.delete(_reset_key(payload.token))
        recruiter_id, _ = await pipe.execute()
    finally:
        await redis.aclose()

    if recruiter_id is None:
        raise HTTPException(status_code=400, detail="This reset link is invalid or has expired")

    recruiter = await db.get(Recruiter, uuid.UUID(recruiter_id))
    if recruiter is None or not recruiter.is_active:
        raise HTTPException(status_code=400, detail="This reset link is invalid or has expired")

    recruiter.hashed_password = security.hash_password(payload.new_password)
    await db.commit()

    return ForgotPasswordResponse(detail="Password updated — you can now log in with your new password.")
