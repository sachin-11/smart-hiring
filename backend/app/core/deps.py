import uuid

from fastapi import Depends, HTTPException
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
