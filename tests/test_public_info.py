"""Automated unit tests for Public Information API, Security Validation & HTML views."""

import io
import pytest
from PIL import Image
from httpx import AsyncClient
from sqlalchemy import select
from app.models.access_log import AccessLog, AuditActionType


def create_test_image_bytes(format="PNG") -> bytes:
    """Helper to create dummy image bytes."""
    buf = io.BytesIO()
    img = Image.new("RGB", (100, 100), color=(50, 100, 150))
    img.save(buf, format=format)
    return buf.getvalue()


async def register_owner_and_image(client: AsyncClient, email: str = "owner@vault.com"):
    """Helper to create an owner and an active registered image."""
    reg_user = await client.post("/api/v1/auth/register", json={
        "email": email,
        "password": "Password123!",
        "full_name": "Vault Image Owner",
        "role": "owner"
    })
    assert reg_user.status_code == 201
    token = reg_user.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    img_bytes = create_test_image_bytes()
    files = {"file": ("test.png", img_bytes, "image/png")}
    data = {
        "title": "Initial Public Title",
        "description": "Initial Public Description"
    }

    reg_res = await client.post("/api/v1/images/register", files=files, data=data, headers=headers)
    assert reg_res.status_code == 201
    return reg_res.json()["public_image_uid"], token


@pytest.mark.asyncio
async def test_public_info_anonymous_view_and_audit(client: AsyncClient, db_session):
    """Test public viewing without authentication returns 200 and logs view_public."""
    public_uid, _ = await register_owner_and_image(client, "anonview@vault.com")

    # Anonymous request (no token/cookie)
    res = await client.get(f"/api/v1/public-info/{public_uid}")
    assert res.status_code == 200
    data = res.json()

    assert data["public_image_uid"] == public_uid
    assert data["title"] == "Initial Public Title"
    assert data["description"] == "Initial Public Description"
    assert data["has_private_vault"] is False

    # Check access_logs for AuditActionType.VIEW_PUBLIC
    audit_stmt = select(AccessLog).where(AccessLog.action_type == AuditActionType.VIEW_PUBLIC)
    logs = (await db_session.execute(audit_stmt)).scalars().all()
    assert len(logs) >= 1
    assert logs[-1].confidence_score == 1.0


@pytest.mark.asyncio
async def test_owner_can_update_public_info(client: AsyncClient):
    """Test image owner can update public details successfully."""
    public_uid, token = await register_owner_and_image(client, "updateowner@vault.com")
    headers = {"Authorization": f"Bearer {token}"}

    update_payload = {
        "title": "Acme Global Security Logo",
        "description": "Updated corporate brand description.",
        "website_url": "https://acme.org",
        "contact_email": "press@acme.org",
        "contact_phone": "+1 (555) 019-2834",
        "services_json": [{"name": "Zero-Trust"}, {"name": "Optical Keys"}]
    }

    put_res = await client.put(f"/api/v1/public-info/{public_uid}", json=update_payload, headers=headers)
    assert put_res.status_code == 200
    data = put_res.json()

    assert data["title"] == "Acme Global Security Logo"
    assert data["website_url"] == "https://acme.org"
    assert data["contact_email"] == "press@acme.org"
    assert len(data["services_json"]) == 2

    # Verify retrieval
    get_res = await client.get(f"/api/v1/public-info/{public_uid}")
    assert get_res.status_code == 200
    assert get_res.json()["title"] == "Acme Global Security Logo"


@pytest.mark.asyncio
async def test_non_owner_cannot_update_public_info(client: AsyncClient):
    """Test that another owner cannot edit an image they do not own (403 Forbidden)."""
    # 1. Owner 1 registers image
    public_uid, _ = await register_owner_and_image(client, "owner1@vault.com")

    # 2. Owner 2 registers account
    owner2 = await client.post("/api/v1/auth/register", json={
        "email": "owner2@vault.com",
        "password": "Password123!",
        "full_name": "Second Owner",
        "role": "owner"
    })
    token2 = owner2.json()["access_token"]
    headers2 = {"Authorization": f"Bearer {token2}"}

    # 3. Owner 2 attempts to edit Owner 1's image
    put_res = await client.put(
        f"/api/v1/public-info/{public_uid}",
        json={"title": "Hacked Title"},
        headers=headers2
    )
    assert put_res.status_code == 403
    assert "Access denied" in put_res.json()["detail"]


@pytest.mark.asyncio
async def test_unauthenticated_update_rejected(client: AsyncClient):
    """Test unauthenticated PUT request is rejected with 401 Unauthorized."""
    public_uid, _ = await register_owner_and_image(client, "noauth@vault.com")
    client.cookies.clear()

    put_res = await client.put(
        f"/api/v1/public-info/{public_uid}",
        json={"title": "Unauthorized Title"}
    )
    assert put_res.status_code == 401


@pytest.mark.asyncio
async def test_malicious_website_url_rejected(client: AsyncClient):
    """Test that malicious URLs like javascript:alert(1) are rejected with 422."""
    public_uid, token = await register_owner_and_image(client, "xssowner@vault.com")
    headers = {"Authorization": f"Bearer {token}"}

    # Attempt XSS payload in website_url
    bad_payload = {
        "title": "Valid Title",
        "website_url": "javascript:alert(document.cookie)"
    }
    put_res = await client.put(f"/api/v1/public-info/{public_uid}", json=bad_payload, headers=headers)
    assert put_res.status_code == 422


@pytest.mark.asyncio
async def test_nonexistent_image_returns_404(client: AsyncClient):
    """Test 404 returned for unknown public_image_uid."""
    res_get = await client.get("/api/v1/public-info/IMG-NOTFOUND99")
    assert res_get.status_code == 404

    # With valid auth
    reg_user = await client.post("/api/v1/auth/register", json={
        "email": "admin404@vault.com",
        "password": "Password123!",
        "full_name": "Admin Tester",
        "role": "admin"
    })
    token = reg_user.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    res_put = await client.put(
        "/api/v1/public-info/IMG-NOTFOUND99",
        json={"title": "Test Title"},
        headers=headers
    )
    assert res_put.status_code == 404


@pytest.mark.asyncio
async def test_public_and_editor_html_pages_rendered(client: AsyncClient):
    """Test that public view and editor HTML templates render successfully."""
    public_uid, _ = await register_owner_and_image(client, "htmlowner@vault.com")

    # Test /public/{public_image_uid}
    res_view = await client.get(f"/public/{public_uid}")
    assert res_view.status_code == 200
    assert "Verified Optical Record" in res_view.text
    assert "Encrypted Tier 2 Private Vault" in res_view.text
    assert public_uid in res_view.text

    # Test /images/{public_image_uid}/edit
    res_edit = await client.get(f"/images/{public_uid}/edit")
    assert res_edit.status_code == 200
    assert "Edit Image Vault" in res_edit.text
    assert "Tab 1: Public Information" in res_edit.text
    assert "Tab 2: Encrypted Private Vault" in res_edit.text
    assert public_uid in res_edit.text
