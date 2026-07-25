from httpx import AsyncClient

# These only exercise the synchronous validation path in POST /resume/upload
# (extension/size/empty-file checks, which run before the candidate row is
# committed and the background parsing task is scheduled) — deliberately not
# testing a full parse, which would make a real LLM call per test run.


async def test_upload_requires_auth(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/resume/upload", files={"file": ("resume.pdf", b"%PDF-1.4 fake", "application/pdf")})
    assert resp.status_code == 401


async def test_upload_rejects_unsupported_extension(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    resp = await client.post(
        "/api/v1/resume/upload",
        files={"file": ("resume.txt", b"plain text resume", "text/plain")},
        headers=auth_headers,
    )
    assert resp.status_code == 400


async def test_upload_rejects_empty_file(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    resp = await client.post(
        "/api/v1/resume/upload",
        files={"file": ("resume.pdf", b"", "application/pdf")},
        headers=auth_headers,
    )
    assert resp.status_code == 400


async def test_resume_status_404_for_unknown_candidate(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    resp = await client.get(
        "/api/v1/resume/00000000-0000-0000-0000-000000000000/status", headers=auth_headers
    )
    assert resp.status_code == 404
