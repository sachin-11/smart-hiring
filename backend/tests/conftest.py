import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core import redis_client, security
from app.core.database import AsyncSessionLocal, engine
from app.main import app
from app.models.candidate import Candidate
from app.models.job import Job
from app.models.recruiter import Recruiter

# Real Postgres/Redis/S3 — this project's convention (see MODULE_*_SETUP.md) is
# to verify against actual services rather than mocks, so these tests hit the
# same dev DB the app itself uses. Everything created here is explicitly
# cleaned up in fixture teardown.


@pytest_asyncio.fixture(autouse=True)
async def _fresh_pools_per_test() -> AsyncIterator[None]:
    """pytest-asyncio gives each test function its own event loop, but the
    app's DB engine and Redis connection pool are both created once at import
    time and bound to whichever loop first uses them. Resetting both after
    every test forces fresh pools to be lazily created in the next test's own
    loop — otherwise the 2nd+ test that touches the DB or Redis fails with
    'RuntimeError: Event loop is closed' (or, for Redis, just silently uses a
    dead connection and the request 500s)."""
    yield
    await engine.dispose()
    await redis_client._pool.disconnect()


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def recruiter() -> AsyncIterator[tuple[Recruiter, str]]:
    """A throwaway recruiter + a real access token for it, created directly via
    the DB (not the rate-limited /auth/register endpoint)."""
    async with AsyncSessionLocal() as db:
        r = Recruiter(
            id=uuid.uuid4(),
            email=f"pytest-{uuid.uuid4().hex[:8]}@example.com",
            hashed_password=security.hash_password("Test-Password-123!"),
            full_name="Pytest Recruiter",
        )
        db.add(r)
        await db.commit()
        await db.refresh(r)

    token = security.create_access_token(r.id)
    yield r, token

    async with AsyncSessionLocal() as db:
        fresh = await db.get(Recruiter, r.id)
        if fresh is not None:
            await db.delete(fresh)
            await db.commit()


@pytest_asyncio.fixture
async def job() -> AsyncIterator[Job]:
    async with AsyncSessionLocal() as db:
        j = Job(
            id=uuid.uuid4(),
            title="Pytest Test Job",
            description="Throwaway job created by the automated test suite.",
        )
        db.add(j)
        await db.commit()
        await db.refresh(j)

    yield j

    async with AsyncSessionLocal() as db:
        fresh = await db.get(Job, j.id)
        if fresh is not None:
            await db.delete(fresh)
            await db.commit()


@pytest_asyncio.fixture
async def candidate() -> AsyncIterator[Candidate]:
    async with AsyncSessionLocal() as db:
        c = Candidate(
            id=uuid.uuid4(),
            full_name="Pytest Candidate",
            email=f"pytest-candidate-{uuid.uuid4().hex[:8]}@example.com",
        )
        db.add(c)
        await db.commit()
        await db.refresh(c)

    yield c

    async with AsyncSessionLocal() as db:
        fresh = await db.get(Candidate, c.id)
        if fresh is not None:
            await db.delete(fresh)
            await db.commit()


@pytest.fixture
def auth_headers(recruiter: tuple[Recruiter, str]) -> dict[str, str]:
    _, token = recruiter
    return {"Authorization": f"Bearer {token}"}
