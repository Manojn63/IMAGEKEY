"""Test suite for Data Sync Status and Anti-Stale Cache-Control Headers."""

import io
import pytest
from httpx import AsyncClient
from PIL import Image


def create_test_image_bytes(color: str = "red") -> bytes:
    """Helper to create dummy image bytes."""
    buf = io.BytesIO()
    img = Image.new("RGB", (100, 100), color=color)
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.asyncio
async def test_api_sync_status_endpoints(client: AsyncClient):
    """Verify both /api/sync-status and /api/v1/sync-status return valid sync schema."""
    # 1. Root /api/sync-status
    res1 = await client.get("/api/sync-status")
    assert res1.status_code == 200
    data1 = res1.json()
    assert "version" in data1
    assert isinstance(data1["version"], str)
    assert len(data1["version"]) > 0
    assert "timestamp" in data1
    assert isinstance(data1["timestamp"], int)
    assert data1["status"] == "ok"

    # 2. V1 prefix /api/v1/sync-status
    res2 = await client.get("/api/v1/sync-status")
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["version"] == data1["version"]
    assert data2["timestamp"] == data1["timestamp"]
    assert data2["status"] == "ok"


@pytest.mark.asyncio
async def test_anti_stale_cache_control_headers(client: AsyncClient):
    """Verify dynamic API responses receive strict no-store / no-cache headers."""
    # Check sync-status
    sync_res = await client.get("/api/sync-status")
    assert sync_res.status_code == 200
    cache_ctrl = sync_res.headers.get("Cache-Control", "")
    assert "no-store" in cache_ctrl
    assert "no-cache" in cache_ctrl
    assert "must-revalidate" in cache_ctrl
    assert sync_res.headers.get("Pragma") == "no-cache"

    # Check health endpoint
    health_res = await client.get("/health")
    assert health_res.status_code == 200
    h_cache = health_res.headers.get("Cache-Control", "")
    assert "no-store" in h_cache
    assert "no-cache" in h_cache


@pytest.mark.asyncio
async def test_sync_version_changes_on_data_mutation(client: AsyncClient):
    """Verify that registering a new image changes the sync version hash."""
    # Initial sync status
    res_before = await client.get("/api/sync-status")
    assert res_before.status_code == 200
    v_before = res_before.json()["version"]

    # Register an owner and upload an image
    reg_user = await client.post("/api/v1/auth/register", json={
        "email": "sync_owner@example.com",
        "full_name": "Sync Test Owner",
        "password": "Password123!",
        "role": "owner"
    })
    assert reg_user.status_code == 201
    token = reg_user.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Register image
    img_bytes = create_test_image_bytes("blue")
    files = {"file": ("sync_test.png", img_bytes, "image/png")}
    data = {"title": "Sync Test Asset"}

    res_upload = await client.post("/api/v1/images/register", files=files, data=data, headers=headers)
    assert res_upload.status_code == 201

    # Check sync status after upload
    res_after = await client.get("/api/sync-status")
    assert res_after.status_code == 200
    v_after = res_after.json()["version"]

    # Version hash must have changed
    assert v_after != v_before
