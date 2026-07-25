import uuid

from httpx import AsyncClient

from app.core import security
from app.core.database import AsyncSessionLocal
from app.models.candidate import Candidate
from app.models.interview import Interview, InterviewStatus
from app.models.job import Job

# Only the auth-gating branches are exercised here — they run before any LLM
# call, so these stay fast/free. The scored multi-turn conversation itself was
# already verified manually against the running app (see MODULE_9_SETUP.md).


async def test_start_interview_requires_recruiter_auth(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/interview/start",
        json={"candidate_id": str(uuid.uuid4()), "job_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 401


async def test_answer_requires_auth_or_token(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/interview/answer",
        data={"session_id": str(uuid.uuid4()), "answer_text": "hello"},
    )
    assert resp.status_code == 401


async def _make_interview(candidate: Candidate, job: Job) -> Interview:
    async with AsyncSessionLocal() as db:
        interview = Interview(candidate_id=candidate.id, job_id=job.id, status=InterviewStatus.IN_PROGRESS)
        db.add(interview)
        await db.commit()
        await db.refresh(interview)
        return interview


async def test_transcript_requires_auth_or_token(
    client: AsyncClient, candidate: Candidate, job: Job
) -> None:
    interview = await _make_interview(candidate, job)
    try:
        resp = await client.get(f"/api/v1/interview/{interview.id}/transcript")
        assert resp.status_code == 401
    finally:
        async with AsyncSessionLocal() as db:
            fresh = await db.get(Interview, interview.id)
            if fresh is not None:
                await db.delete(fresh)
                await db.commit()


async def test_transcript_accepts_recruiter_token(
    client: AsyncClient, auth_headers: dict[str, str], candidate: Candidate, job: Job
) -> None:
    interview = await _make_interview(candidate, job)
    try:
        resp = await client.get(f"/api/v1/interview/{interview.id}/transcript", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["session_id"] == str(interview.id)
    finally:
        async with AsyncSessionLocal() as db:
            fresh = await db.get(Interview, interview.id)
            if fresh is not None:
                await db.delete(fresh)
                await db.commit()


async def test_transcript_accepts_matching_magic_link_token(
    client: AsyncClient, candidate: Candidate, job: Job
) -> None:
    interview = await _make_interview(candidate, job)
    try:
        token = security.create_interview_access_token(interview.id)
        resp = await client.get(f"/api/v1/interview/{interview.id}/transcript?token={token}")
        assert resp.status_code == 200
    finally:
        async with AsyncSessionLocal() as db:
            fresh = await db.get(Interview, interview.id)
            if fresh is not None:
                await db.delete(fresh)
                await db.commit()


async def test_transcript_rejects_token_for_a_different_session(
    client: AsyncClient, candidate: Candidate, job: Job
) -> None:
    interview = await _make_interview(candidate, job)
    try:
        # A validly-signed token, but scoped to a different session_id.
        mismatched_token = security.create_interview_access_token(uuid.uuid4())
        resp = await client.get(f"/api/v1/interview/{interview.id}/transcript?token={mismatched_token}")
        assert resp.status_code == 401
    finally:
        async with AsyncSessionLocal() as db:
            fresh = await db.get(Interview, interview.id)
            if fresh is not None:
                await db.delete(fresh)
                await db.commit()
