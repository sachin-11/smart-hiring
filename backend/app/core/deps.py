import uuid

from fastapi import Depends, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.database import get_db
from app.models.recruiter import Recruiter

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_recruiter(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> Recruiter:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated", headers={"WWW-Authenticate": "Bearer"})

    try:
        claims = security.decode_token(credentials.credentials, expected_type=security.ACCESS_TOKEN_TYPE)
    except security.TokenError as exc:
        raise HTTPException(status_code=401, detail=str(exc), headers={"WWW-Authenticate": "Bearer"}) from exc

    recruiter = await db.get(Recruiter, uuid.UUID(claims["sub"]))
    if recruiter is None or not recruiter.is_active:
        raise HTTPException(status_code=401, detail="Recruiter account no longer exists or is inactive")

    return recruiter


async def recruiter_from_credentials(
    credentials: HTTPAuthorizationCredentials | None, db: AsyncSession
) -> Recruiter | None:
    if credentials is None:
        return None
    try:
        claims = security.decode_token(credentials.credentials, expected_type=security.ACCESS_TOKEN_TYPE)
    except security.TokenError:
        return None
    recruiter = await db.get(Recruiter, uuid.UUID(claims["sub"]))
    if recruiter is None or not recruiter.is_active:
        return None
    return recruiter


def interview_token_matches(token: str | None, session_id: uuid.UUID) -> bool:
    """True if `token` is a valid, unexpired magic-link interview-access token
    scoped to exactly this session_id."""
    if not token:
        return False
    try:
        claims = security.decode_token(token, expected_type=security.INTERVIEW_ACCESS_TOKEN_TYPE)
    except security.TokenError:
        return False
    return claims.get("sub") == str(session_id)


async def require_recruiter_or_interview_access(
    session_id: uuid.UUID,
    token: str | None = Query(default=None),
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Allows either a logged-in recruiter (any recruiter — same as every
    other route) OR a candidate holding a valid magic-link token scoped to
    this exact session_id. Use on candidate-facing interview endpoints that
    take session_id as a path param; for the one that takes it as a Form
    field instead (POST /interview/answer), call interview_token_matches()
    and recruiter_from_credentials() directly since FastAPI dependencies
    can't cleanly share a path-param binding with a form-encoded route."""
    recruiter = await recruiter_from_credentials(credentials, db)
    if recruiter is not None:
        return
    if interview_token_matches(token, session_id):
        return
    raise HTTPException(status_code=401, detail="Not authenticated")
