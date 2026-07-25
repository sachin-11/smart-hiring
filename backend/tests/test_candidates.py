import uuid

from httpx import AsyncClient

from app.core.database import AsyncSessionLocal
from app.models.candidate import Candidate
from app.models.interview import Interview, InterviewStatus
from app.models.job import Job
from app.models.report import Report


async def test_delete_candidate_requires_auth(client: AsyncClient, candidate: Candidate) -> None:
    resp = await client.delete(f"/api/v1/candidates/{candidate.id}")
    assert resp.status_code == 401


async def test_delete_unknown_candidate_404(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    resp = await client.delete(
        "/api/v1/candidates/00000000-0000-0000-0000-000000000000", headers=auth_headers
    )
    assert resp.status_code == 404


async def test_delete_candidate_cascades_related_rows(
    client: AsyncClient, auth_headers: dict[str, str], candidate: Candidate, job: Job
) -> None:
    async with AsyncSessionLocal() as db:
        interview = Interview(candidate_id=candidate.id, job_id=job.id, status=InterviewStatus.COMPLETED)
        db.add(interview)
        await db.flush()
        report = Report(
            interview_id=interview.id,
            candidate_id=candidate.id,
            job_id=job.id,
            report_data={"foo": "bar"},
            overall_score=80.0,
            recommendation="hire",
        )
        db.add(report)
        await db.commit()
        interview_id, report_id = interview.id, report.id

    resp = await client.delete(f"/api/v1/candidates/{candidate.id}", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["interviews_deleted"] == 1
    assert body["reports_deleted"] == 1

    async with AsyncSessionLocal() as db:
        assert await db.get(Candidate, candidate.id) is None
        assert await db.get(Interview, interview_id) is None
        assert await db.get(Report, report_id) is None
