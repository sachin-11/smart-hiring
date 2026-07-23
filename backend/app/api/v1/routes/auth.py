import logging
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.config import settings
from app.core.database import get_db
from app.core.redis_client import get_redis_client
from app.models.recruiter import Recruiter
from app.schemas.auth import LoginRequest, RecruiterResponse, RefreshRequest, RegisterRequest, TokenResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

_REFRESH_SESSION_PREFIX = "auth:refresh"


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
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
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
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
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
