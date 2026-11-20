"""Automated tests for Private Vault, Permission Engine, and Access Control."""

import io
import pytest
from datetime import datetime, timezone, timedelta
from PIL import Image
from httpx import AsyncClient
from sqlalchemy import select

from app.models.access_log import AccessLog, AuditActionType


def create_test_image(format="PNG") -> bytes:
    """Helper to create dummy image bytes."""
    buf = io.BytesIO()
    img = Image.new("RGB", (100, 100), color=(30, 60, 90))
    img.save(buf, format=format)
    return buf.getvalue()


async def setup_owner_and_image(client: AsyncClient, email: str = "pvt_owner@vault.com"):
    """Helper creating owner user and registering an image."""
    client.cookies.clear()
    reg_user = await client.post("/api/v1/auth/register", json={
        "email": email,
        "password": "Password123!",
        "full_name": "Private Vault Owner",
        "role": "owner"
    })
    assert reg_user.status_code == 201
    owner_data = reg_user.json()
    owner_token = owner_data["access_token"]
    owner_id = owner_data["user"]["id"]

    headers = {"Authorization": f"Bearer {owner_token}"}
    files = {"file": ("test.png", create_test_image(), "image/png")}
    data = {"title": "Classified Asset", "description": "Top secret optical key"}

    reg_img = await client.post("/api/v1/images/register", files=files, data=data, headers=headers)
    assert reg_img.status_code == 201
    uid = reg_img.json()["public_image_uid"]

    client.cookies.clear()
    return uid, owner_token, owner_id


async def register_viewer(client: AsyncClient, email: str = "viewer@vault.com"):
    """Helper creating viewer user."""
    client.cookies.clear()
    reg_viewer = await client.post("/api/v1/auth/register", json={
        "email": email,
        "password": "Password123!",
        "full_name": "Standard Viewer",
        "role": "viewer"
    })
    assert reg_viewer.status_code == 201
    v_data = reg_viewer.json()
    client.cookies.clear()
    return v_data["access_token"], v_data["user"]["id"], email


@pytest.mark.asyncio
async def test_unauthenticated_private_vault_rejected_401(client: AsyncClient):
    """Test accessing private vault without auth returns 401 Unauthorized."""
    uid, _, _ = await setup_owner_and_image(client, "noauth_pvt@vault.com")
    client.cookies.clear()

    res = await client.get(f"/api/v1/private-info/{uid}")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_ungranted_viewer_rejected_403_and_logs_unauthorized(client: AsyncClient, db_session):
    """Test ungranted viewer receives 403 Forbidden and records UNAUTHORIZED_ATTEMPT."""
    uid, _, _ = await setup_owner_and_image(client, "ungranted_owner@vault.com")
    viewer_token, _, _ = await register_viewer(client, "ungranted_viewer@vault.com")

    client.cookies.clear()
    headers = {"Authorization": f"Bearer {viewer_token}"}
    res = await client.get(f"/api/v1/private-info/{uid}", headers=headers)

    assert res.status_code == 403
    assert "Access denied" in res.json()["detail"]

    # Verify audit log entry was written
    audit_stmt = select(AccessLog).where(AccessLog.action_type == AuditActionType.UNAUTHORIZED_ATTEMPT)
    logs = (await db_session.execute(audit_stmt)).scalars().all()
    assert len(logs) >= 1
    assert logs[-1].confidence_score == 0.0


@pytest.mark.asyncio
async def test_owner_grants_view_permission_and_viewer_succeeds(client: AsyncClient, db_session):
    """Test granting view_private permission enables viewer access and records VIEW_PRIVATE."""
    uid, owner_token, _ = await setup_owner_and_image(client, "perm_owner@vault.com")
    viewer_token, viewer_id, viewer_email = await register_viewer(client, "authorized_viewer@vault.com")

    # 1. Owner grants view_private permission
    client.cookies.clear()
    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    grant_payload = {
        "email": viewer_email,
        "access_level": "view_private",
    }
    grant_res = await client.post(f"/api/v1/permissions/{uid}", json=grant_payload, headers=owner_headers)
    assert grant_res.status_code == 201
    assert grant_res.json()["user_email"] == viewer_email

    # 2. Viewer accesses private vault
    client.cookies.clear()
    viewer_headers = {"Authorization": f"Bearer {viewer_token}"}
    view_res = await client.get(f"/api/v1/private-info/{uid}", headers=viewer_headers)

    assert view_res.status_code == 200
    data = view_res.json()
    assert data["public_image_uid"] == uid
    assert data["user_access_level"] == "view_private"

    # 3. Verify audit log has VIEW_PRIVATE
    audit_stmt = select(AccessLog).where(AccessLog.action_type == AuditActionType.VIEW_PRIVATE)
    logs = (await db_session.execute(audit_stmt)).scalars().all()
    assert len(logs) >= 1


@pytest.mark.asyncio
async def test_expired_permission_is_rejected_403(client: AsyncClient):
    """Test expired permission strictly results in 403 Forbidden."""
    uid, owner_token, _ = await setup_owner_and_image(client, "exp_owner@vault.com")
    viewer_token, _, viewer_email = await register_viewer(client, "expired_viewer@vault.com")

    # Grant permission that expired 2 hours ago
    past_time = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    client.cookies.clear()
    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    grant_payload = {
        "email": viewer_email,
        "access_level": "view_private",
        "expires_at": past_time,
    }
    grant_res = await client.post(f"/api/v1/permissions/{uid}", json=grant_payload, headers=owner_headers)
    assert grant_res.status_code == 201
    assert grant_res.json()["is_expired"] is True

    # Viewer attempts access
    client.cookies.clear()
    viewer_headers = {"Authorization": f"Bearer {viewer_token}"}
    view_res = await client.get(f"/api/v1/private-info/{uid}", headers=viewer_headers)
    assert view_res.status_code == 403


@pytest.mark.asyncio
async def test_revoking_permission_blocks_access(client: AsyncClient):
    """Test revoking permission immediately cuts off access."""
    uid, owner_token, _ = await setup_owner_and_image(client, "revoke_owner@vault.com")
    viewer_token, viewer_id, viewer_email = await register_viewer(client, "revoked_viewer@vault.com")

    # Grant permission
    client.cookies.clear()
    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    await client.post(
        f"/api/v1/permissions/{uid}",
        json={"email": viewer_email, "access_level": "view_private"},
        headers=owner_headers
    )

    # Viewer has access
    client.cookies.clear()
    viewer_headers = {"Authorization": f"Bearer {viewer_token}"}
    res1 = await client.get(f"/api/v1/private-info/{uid}", headers=viewer_headers)
    assert res1.status_code == 200

    # Owner revokes permission
    client.cookies.clear()
    del_res = await client.delete(f"/api/v1/permissions/{uid}/{viewer_id}", headers=owner_headers)
    assert del_res.status_code == 200

    # Viewer access is immediately denied
    client.cookies.clear()
    res2 = await client.get(f"/api/v1/private-info/{uid}", headers=viewer_headers)
    assert res2.status_code == 403


@pytest.mark.asyncio
async def test_non_owner_cannot_manage_permissions_403(client: AsyncClient):
    """Test unauthorized users cannot list, grant, or revoke permissions."""
    uid, _, _ = await setup_owner_and_image(client, "realowner@vault.com")
    stranger_token, stranger_id, _ = await register_viewer(client, "stranger@vault.com")

    client.cookies.clear()
    headers = {"Authorization": f"Bearer {stranger_token}"}

    # Cannot list
    assert (await client.get(f"/api/v1/permissions/{uid}", headers=headers)).status_code == 403

    # Cannot grant
    assert (await client.post(
        f"/api/v1/permissions/{uid}",
        json={"email": "victim@vault.com", "access_level": "view_private"},
        headers=headers
    )).status_code == 403

    # Cannot revoke
    assert (await client.delete(f"/api/v1/permissions/{uid}/{stranger_id}", headers=headers)).status_code == 403


@pytest.mark.asyncio
async def test_owner_and_edit_role_can_update_private_info(client: AsyncClient):
    """Test updating private info by owner and by user granted EDIT access."""
    uid, owner_token, _ = await setup_owner_and_image(client, "editor_owner@vault.com")
    editor_token, editor_id, editor_email = await register_viewer(client, "editor_user@vault.com")
    viewer_token, _, viewer_email = await register_viewer(client, "viewonly_user@vault.com")

    # 1. Owner updates private vault
    client.cookies.clear()
    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    pvt_payload = {
        "confidential_notes": "Owner initial secret instructions",
        "internal_data_json": {"api_key": "SEC-999", "tier": "A"},
        "document_paths_json": ["specs.pdf"]
    }
    put_owner = await client.put(f"/api/v1/private-info/{uid}", json=pvt_payload, headers=owner_headers)
    assert put_owner.status_code == 200
    assert put_owner.json()["confidential_notes"] == "Owner initial secret instructions"

    # 2. Owner grants EDIT permission to editor_user
    client.cookies.clear()
    await client.post(
        f"/api/v1/permissions/{uid}",
        json={"email": editor_email, "access_level": "edit"},
        headers=owner_headers
    )

    # 3. Editor updates private vault
    client.cookies.clear()
    editor_headers = {"Authorization": f"Bearer {editor_token}"}
    editor_payload = {
        "confidential_notes": "Editor updated confidential notes",
        "internal_data_json": {"api_key": "SEC-NEW", "tier": "A+"},
        "document_paths_json": ["specs_v2.pdf"]
    }
    put_editor = await client.put(f"/api/v1/private-info/{uid}", json=editor_payload, headers=editor_headers)
    assert put_editor.status_code == 200
    assert put_editor.json()["confidential_notes"] == "Editor updated confidential notes"

    # 4. View-only user attempts to edit -> 403
    client.cookies.clear()
    await client.post(
        f"/api/v1/permissions/{uid}",
        json={"email": viewer_email, "access_level": "view_private"},
        headers=owner_headers
    )
    client.cookies.clear()
    viewer_headers = {"Authorization": f"Bearer {viewer_token}"}
    put_viewer = await client.put(f"/api/v1/private-info/{uid}", json=editor_payload, headers=viewer_headers)
    assert put_viewer.status_code == 403


@pytest.mark.asyncio
async def test_html_pages_rendered_for_phase6(client: AsyncClient):
    """Test HTML templates for dashboard, private vault, and permissions manager render."""
    uid, _, _ = await setup_owner_and_image(client, "htmlphase6@vault.com")
    client.cookies.clear()

    # Dashboard page
    res_dash = await client.get("/dashboard")
    assert res_dash.status_code == 200
    assert "Vault Dashboard" in res_dash.text
    assert "Your Registered Optical Keys" in res_dash.text

    # Private Vault page
    res_vault = await client.get(f"/vault/{uid}")
    assert res_vault.status_code == 200
    assert "Tier 2 Encrypted Private Vault" in res_vault.text
    assert uid in res_vault.text

    # Permissions Manager page
    res_perm = await client.get(f"/images/{uid}/permissions")
    assert res_perm.status_code == 200
    assert "Vault Clearance Controls" in res_perm.text
    assert "Authorized Clearance Roster" in res_perm.text
    assert uid in res_perm.text
