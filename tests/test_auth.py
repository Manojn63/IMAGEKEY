"""Automated unit tests for Authentication & RBAC."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_and_login_flow(client: AsyncClient):
    """Test full cycle: register -> login -> profile check -> logout."""
    # 1. Register new user
    reg_payload = {
        "email": "testowner@imagekey.io",
        "password": "SecurePassword123!",
        "full_name": "Test Image Owner",
        "role": "owner"
    }
    reg_res = await client.post("/api/v1/auth/register", json=reg_payload)
    assert reg_res.status_code == 201, reg_res.text
    data = reg_res.json()
    assert "access_token" in data
    assert data["user"]["email"] == "testowner@imagekey.io"
    assert data["user"]["role"] == "owner"
    token = data["access_token"]

    # 2. Duplicate registration should return 409 Conflict
    dup_res = await client.post("/api/v1/auth/register", json=reg_payload)
    assert dup_res.status_code == 409

    # 3. Login with credentials
    login_res = await client.post("/api/v1/auth/login", json={
        "email": "testowner@imagekey.io",
        "password": "SecurePassword123!"
    })
    assert login_res.status_code == 200
    login_data = login_res.json()
    assert "access_token" in login_data

    # 4. Fetch authenticated profile via Bearer header
    me_res = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert me_res.status_code == 200
    me_data = me_res.json()
    assert me_data["email"] == "testowner@imagekey.io"

    # 5. Logout
    logout_res = await client.post("/api/v1/auth/logout")
    assert logout_res.status_code == 200


@pytest.mark.asyncio
async def test_invalid_login_rejection(client: AsyncClient):
    """Test rejection of non-existent user or bad password."""
    res = await client.post("/api/v1/auth/login", json={
        "email": "ghost@domain.com",
        "password": "WrongPassword123"
    })
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_invalid_jwt_uuid_rejection(client: AsyncClient):
    """Test that non-UUID subject in JWT is rejected safely without server crash."""
    from app.core.security import create_access_token
    # Token with non-UUID subject string
    malformed_token = create_access_token({"sub": "not-a-valid-uuid", "email": "test@test.com"})
    res = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {malformed_token}"}
    )
    assert res.status_code == 401
    assert "Could not validate authentication credentials" in res.json()["detail"]


@pytest.mark.asyncio
async def test_cookie_authentication(client: AsyncClient):
    """Test authentication via HTTP-only cookie."""
    # 1. Register
    reg_payload = {
        "email": "cookieuser@imagekey.io",
        "password": "SecurePassword123!",
        "full_name": "Cookie Tester",
        "role": "viewer"
    }
    reg_res = await client.post("/api/v1/auth/register", json=reg_payload)
    assert reg_res.status_code == 201
    cookie_token = reg_res.json()["access_token"]

    # 2. Access /api/v1/auth/me using Cookie
    client.cookies.set("imagekey_session", cookie_token)
    me_res = await client.get("/api/v1/auth/me")
    assert me_res.status_code == 200
    assert me_res.json()["email"] == "cookieuser@imagekey.io"
