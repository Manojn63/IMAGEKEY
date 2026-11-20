"""Automated unit tests for Admin API, Moderation Controls, and Security Hardening."""

import io
import pytest
from PIL import Image
from httpx import AsyncClient

from app.models.access_log import AuditActionType


def create_test_image(format="PNG") -> bytes:
    """Helper to generate dummy image bytes."""
    buf = io.BytesIO()
    img = Image.new("RGB", (100, 100), color=(120, 80, 40))
    img.save(buf, format=format)
    return buf.getvalue()


async def register_account(client: AsyncClient, email: str, role: str):
    """Helper to register an account and retrieve token and user id."""
    client.cookies.clear()
    res = await client.post("/api/v1/auth/register", json={
        "email": email,
        "password": "SecurePassword123!",
        "full_name": f"{role.capitalize()} User",
        "role": role,
    })
    assert res.status_code == 201
    data = res.json()
    client.cookies.clear()
    return data["access_token"], data["user"]["id"]


@pytest.mark.asyncio
async def test_admin_rbac_protection(client: AsyncClient):
    """Test non-admin roles (viewer, owner) are rejected with 403 Forbidden from admin endpoints."""
    viewer_token, _ = await register_account(client, "viewer_rbac@admin.com", "viewer")
    owner_token, _ = await register_account(client, "owner_rbac@admin.com", "owner")
    admin_token, _ = await register_account(client, "admin_rbac@admin.com", "admin")

    # 1. Viewer attempt -> 403
    client.cookies.clear()
    v_res = await client.get("/api/v1/admin/overview", headers={"Authorization": f"Bearer {viewer_token}"})
    assert v_res.status_code == 403

    # 2. Owner attempt -> 403
    client.cookies.clear()
    o_res = await client.get("/api/v1/admin/overview", headers={"Authorization": f"Bearer {owner_token}"})
    assert o_res.status_code == 403

    # 3. Admin attempt -> 200
    client.cookies.clear()
    a_res = await client.get("/api/v1/admin/overview", headers={"Authorization": f"Bearer {admin_token}"})
    assert a_res.status_code == 200
    assert "total_users" in a_res.json()


@pytest.mark.asyncio
async def test_admin_user_status_moderation(client: AsyncClient):
    """Test admin suspending and re-activating a user, and preventing self-suspension."""
    admin_token, admin_id = await register_account(client, "superadmin@admin.com", "admin")
    target_token, target_id = await register_account(client, "target@user.com", "viewer")

    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # 1. Admin attempts to suspend themselves -> 400 Bad Request
    client.cookies.clear()
    self_res = await client.patch(
        f"/api/v1/admin/users/{admin_id}/status",
        json={"is_active": False},
        headers=admin_headers
    )
    assert self_res.status_code == 400
    assert "cannot suspend their own account" in self_res.json()["detail"]

    # 2. Admin suspends target user -> 200 OK
    client.cookies.clear()
    suspend_res = await client.patch(
        f"/api/v1/admin/users/{target_id}/status",
        json={"is_active": False},
        headers=admin_headers
    )
    assert suspend_res.status_code == 200
    assert suspend_res.json()["is_active"] is False

    # 3. Target user cannot log in when inactive -> 403 Forbidden
    client.cookies.clear()
    login_res = await client.post("/api/v1/auth/login", json={
        "email": "target@user.com",
        "password": "SecurePassword123!"
    })
    assert login_res.status_code == 403
    assert "suspended or inactive" in login_res.json()["detail"]

    # 4. Admin re-activates target user
    client.cookies.clear()
    activate_res = await client.patch(
        f"/api/v1/admin/users/{target_id}/status",
        json={"is_active": True},
        headers=admin_headers
    )
    assert activate_res.status_code == 200
    assert activate_res.json()["is_active"] is True


@pytest.mark.asyncio
async def test_admin_image_suspension_controls(client: AsyncClient):
    """Test suspending an image blocks public view and scanner matches."""
    admin_token, _ = await register_account(client, "imgadmin@admin.com", "admin")
    owner_token, _ = await register_account(client, "imgowner@admin.com", "owner")

    # Owner registers an image
    client.cookies.clear()
    img_bytes = create_test_image()
    files = {"file": ("suspend_test.png", img_bytes, "image/png")}
    data = {"title": "Suspension Candidate"}
    reg_res = await client.post(
        "/api/v1/images/register",
        files=files,
        data=data,
        headers={"Authorization": f"Bearer {owner_token}"}
    )
    assert reg_res.status_code == 201
    uid = reg_res.json()["public_image_uid"]

    # Verify public view active before suspension
    client.cookies.clear()
    assert (await client.get(f"/api/v1/public-info/{uid}")).status_code == 200

    # Admin suspends the image
    client.cookies.clear()
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    suspend_res = await client.patch(
        f"/api/v1/admin/images/{uid}/status",
        json={"status": "suspended"},
        headers=admin_headers
    )
    assert suspend_res.status_code == 200
    assert suspend_res.json()["status"] == "suspended"

    # Suspended image returns 404 from public view
    client.cookies.clear()
    assert (await client.get(f"/api/v1/public-info/{uid}")).status_code == 404

    # Scanner ignores suspended image -> returns NO_MATCH
    scan_files = {"file": ("query.png", img_bytes, "image/png")}
    scan_res = await client.post("/api/v1/scanner/identify", files=scan_files)
    assert scan_res.status_code == 200
    assert scan_res.json()["verdict"] == "NO_MATCH"

    # Admin re-activates image
    client.cookies.clear()
    act_res = await client.patch(
        f"/api/v1/admin/images/{uid}/status",
        json={"status": "active"},
        headers=admin_headers
    )
    assert act_res.status_code == 200
    assert act_res.json()["status"] == "active"

    # Public view is restored
    client.cookies.clear()
    assert (await client.get(f"/api/v1/public-info/{uid}")).status_code == 200


@pytest.mark.asyncio
async def test_admin_logs_filtering(client: AsyncClient):
    """Test retrieving and filtering audit logs."""
    admin_token, _ = await register_account(client, "logadmin@admin.com", "admin")

    client.cookies.clear()
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # Query all logs
    res_all = await client.get("/api/v1/admin/logs", headers=admin_headers)
    assert res_all.status_code == 200
    data_all = res_all.json()
    assert "total" in data_all
    assert isinstance(data_all["logs"], list)

    # Query filtered by action_type=permission_change
    res_filtered = await client.get("/api/v1/admin/logs?action_type=permission_change", headers=admin_headers)
    assert res_filtered.status_code == 200
    data_filt = res_filtered.json()
    for lg in data_filt["logs"]:
        assert lg["action_type"] == "permission_change"


@pytest.mark.asyncio
async def test_http_security_headers_middleware(client: AsyncClient):
    """Verify HTTP security headers are attached to API and page responses."""
    res = await client.get("/health")
    assert res.status_code == 200

    headers = res.headers
    assert headers.get("X-Content-Type-Options") == "nosniff"
    assert headers.get("X-Frame-Options") == "DENY"
    assert headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert headers.get("Permissions-Policy") == "camera=(self)"


@pytest.mark.asyncio
async def test_admin_html_page_rendered(client: AsyncClient):
    """Verify that the Page 10 Admin operations template renders properly."""
    res = await client.get("/admin")
    assert res.status_code == 200
    assert "Admin Operations & Moderation" in res.text
    assert "Live Audit Telemetry" in res.text
    assert "Optical Asset Moderation" in res.text
