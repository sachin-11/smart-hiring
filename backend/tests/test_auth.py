from httpx import AsyncClient

from app.models.recruiter import Recruiter


async def test_login_success(client: AsyncClient, recruiter: tuple[Recruiter, str]) -> None:
    r, _ = recruiter
    resp = await client.post("/api/v1/auth/login", json={"email": r.email, "password": "Test-Password-123!"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["recruiter"]["email"] == r.email


async def test_login_wrong_password(client: AsyncClient, recruiter: tuple[Recruiter, str]) -> None:
    r, _ = recruiter
    resp = await client.post("/api/v1/auth/login", json={"email": r.email, "password": "definitely-wrong"})
    assert resp.status_code == 401


async def test_login_unknown_email(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/login", json={"email": "no-such-recruiter@example.com", "password": "whatever"}
    )
    assert resp.status_code == 401


async def test_protected_route_requires_auth(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/candidates")
    assert resp.status_code == 401


async def test_protected_route_rejects_garbage_token(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/candidates", headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401


async def test_protected_route_accepts_valid_token(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    resp = await client.get("/api/v1/candidates", headers=auth_headers)
    assert resp.status_code == 200
