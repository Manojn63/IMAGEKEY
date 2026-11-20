"""Automated unit tests for Image Registration, EXIF Sanitization, and CV Pipeline."""

import io
import pytest
from PIL import Image
from httpx import AsyncClient


def create_test_image(format="PNG", size=(100, 100), color=(0, 128, 255)) -> bytes:
    """Generate in-memory valid image bytes for testing."""
    buf = io.BytesIO()
    img = Image.new("RGB", size, color=color)
    img.save(buf, format=format)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_owner_image_registration_success(client: AsyncClient):
    """Test full cycle: Owner registers an image -> hashes generated -> listed in my-images."""
    # 1. Register owner account
    reg_user = await client.post("/api/v1/auth/register", json={
        "email": "brandowner@company.com",
        "password": "SecurePassword123!",
        "full_name": "Brand Owner",
        "role": "owner"
    })
    assert reg_user.status_code == 201
    token = reg_user.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Upload valid image
    img_bytes = create_test_image(format="PNG")
    files = {"file": ("logo.png", img_bytes, "image/png")}
    data = {"title": "Company Official Logo", "description": "Primary visual trademark"}

    upload_res = await client.post("/api/v1/images/register", files=files, data=data, headers=headers)
    assert upload_res.status_code == 201, upload_res.text
    payload = upload_res.json()

    assert payload["public_image_uid"].startswith("IMG-")
    assert len(payload["public_image_uid"]) >= 10
    assert payload["phash"] is not None
    assert payload["title"] == "Company Official Logo"
    assert payload["status"] == "active"

    # 3. Verify in my-images
    list_res = await client.get("/api/v1/images/my-images", headers=headers)
    assert list_res.status_code == 200
    my_images = list_res.json()
    assert len(my_images) == 1
    assert my_images[0]["public_image_uid"] == payload["public_image_uid"]


@pytest.mark.asyncio
async def test_viewer_role_upload_forbidden(client: AsyncClient):
    """Test that a user with 'viewer' role is rejected with 403 Forbidden."""
    # 1. Register viewer account
    reg_viewer = await client.post("/api/v1/auth/register", json={
        "email": "receiver@public.com",
        "password": "SecurePassword123!",
        "full_name": "Public Receiver",
        "role": "viewer"
    })
    token = reg_viewer.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Attempt upload
    img_bytes = create_test_image(format="JPEG")
    files = {"file": ("document.jpg", img_bytes, "image/jpeg")}
    data = {"title": "Attempted Upload"}

    res = await client.post("/api/v1/images/register", files=files, data=data, headers=headers)
    assert res.status_code == 403
    assert "Access denied" in res.json()["detail"]


@pytest.mark.asyncio
async def test_unauthenticated_upload_rejected(client: AsyncClient):
    """Test that requests without credentials return 401 Unauthorized."""
    img_bytes = create_test_image()
    files = {"file": ("image.png", img_bytes, "image/png")}
    data = {"title": "Anonymous Upload"}

    res = await client.post("/api/v1/images/register", files=files, data=data)
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_invalid_file_type_rejection(client: AsyncClient):
    """Test that non-image payloads (e.g. text/scripts) are rejected with 400 Bad Request."""
    # Register owner
    reg_owner = await client.post("/api/v1/auth/register", json={
        "email": "secowner@company.com",
        "password": "SecurePassword123!",
        "full_name": "Sec Owner",
        "role": "owner"
    })
    token = reg_owner.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Fake script payload disguised with png filename
    fake_bytes = b"<?php echo 'malicious script'; ?>"
    files = {"file": ("malware.png", fake_bytes, "image/png")}
    data = {"title": "Malicious Test"}

    res = await client.post("/api/v1/images/register", files=files, data=data, headers=headers)
    assert res.status_code == 400
    assert "Corrupted or invalid image" in res.json()["detail"] or "Unsupported" in res.json()["detail"]


@pytest.mark.asyncio
async def test_oversized_file_rejection(client: AsyncClient):
    """Test that files exceeding 5MB are rejected with 413 Request Entity Too Large."""
    reg_owner = await client.post("/api/v1/auth/register", json={
        "email": "largeowner@company.com",
        "password": "SecurePassword123!",
        "full_name": "Large File Tester",
        "role": "owner"
    })
    token = reg_owner.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Generate oversized payload (5MB + 1KB)
    oversized_bytes = b"0" * (5 * 1024 * 1024 + 1024)
    files = {"file": ("huge.jpg", oversized_bytes, "image/jpeg")}
    data = {"title": "Huge Image"}

    res = await client.post("/api/v1/images/register", files=files, data=data, headers=headers)
    assert res.status_code == 413
    assert "exceeds maximum allowed size" in res.json()["detail"]


@pytest.mark.asyncio
async def test_register_page_html(client: AsyncClient):
    """Verify that the Page 4 upload & register template renders correctly."""
    res = await client.get("/register-image")
    assert res.status_code == 200
    assert "Register & Hash Image" in res.text
    assert "Optical Key" in res.text
    assert "dropzone" in res.text


@pytest.mark.asyncio
async def test_image_download_endpoint(client: AsyncClient, db_session):
    """Test image download endpoint: 200 for active, 404 for missing, 403 for suspended."""
    from sqlalchemy import update
    from app.models.image import RegisteredImage, ImageStatus

    # 1. Register owner account
    reg_user = await client.post("/api/v1/auth/register", json={
        "email": "downloadowner@company.com",
        "password": "SecurePassword123!",
        "full_name": "Download Owner",
        "role": "owner"
    })
    assert reg_user.status_code == 201
    token = reg_user.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Upload image
    img_bytes = create_test_image(format="PNG")
    files = {"file": ("download_test.png", img_bytes, "image/png")}
    data = {"title": "Downloadable Artwork"}

    upload_res = await client.post("/api/v1/images/register", files=files, data=data, headers=headers)
    assert upload_res.status_code == 201
    uid = upload_res.json()["public_image_uid"]

    # 3. Test active image download (publicly accessible, no auth required)
    client.cookies.clear()
    res = await client.get(f"/api/v1/images/{uid}/download")
    assert res.status_code == 200
    assert "attachment" in res.headers.get("content-disposition", "")
    assert uid in res.headers.get("content-disposition", "")
    assert len(res.content) > 0

    # 4. Test missing image download -> 404
    res_missing = await client.get("/api/v1/images/IMG-NONEXISTENT/download")
    assert res_missing.status_code == 404

    # 5. Suspend image and verify 403 Forbidden
    await db_session.execute(
        update(RegisteredImage)
        .where(RegisteredImage.public_image_uid == uid)
        .values(status=ImageStatus.SUSPENDED)
    )
    await db_session.commit()

    res_suspended = await client.get(f"/api/v1/images/{uid}/download")
    assert res_suspended.status_code == 403
    assert "suspended" in res_suspended.json()["detail"].lower()

