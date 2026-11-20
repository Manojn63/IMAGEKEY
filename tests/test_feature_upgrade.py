"""Automated unit and integration tests for Smart Playback, PDF Attachments, Permanent Deletion, and Account Sharing."""

import io
from pathlib import Path
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from PIL import Image

from app.core.config import settings


def create_test_image(format="PNG", size=(100, 100), color=(10, 80, 200)) -> bytes:
    """Generate in-memory valid image bytes for testing."""
    buf = io.BytesIO()
    img = Image.new("RGB", size, color=color)
    img.save(buf, format=format)
    return buf.getvalue()


def create_test_pdf() -> bytes:
    """Generate a minimal valid PDF byte sequence."""
    return b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [] /Count 0 >>\nendobj\nxref\n0 3\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \ntrailer\n<< /Root 1 0 R /Size 3 >>\nstartxref\n115\n%%EOF"


@pytest.mark.asyncio
async def test_auto_redirect_smart_playback_metadata(client: AsyncClient):
    """Test updating and retrieving auto_redirect flag for smart content playback."""
    # 1. Register owner and image
    reg = await client.post("/api/v1/auth/register", json={
        "email": "playback_owner@domain.com",
        "password": "Password123!",
        "full_name": "Playback Owner",
        "role": "owner"
    })
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    img_res = await client.post(
        "/api/v1/images/register",
        files={"file": ("key.png", create_test_image(), "image/png")},
        data={"title": "Smart Playback Key"},
        headers=headers,
    )
    assert img_res.status_code == 201
    uid = img_res.json()["public_image_uid"]

    # 2. Update public info with auto_redirect and video/website link
    update_res = await client.put(
        f"/api/v1/public-info/{uid}",
        json={
            "title": "Smart Playback Key",
            "description": "Watch video presentation",
            "website_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "auto_redirect": True,
        },
        headers=headers,
    )
    assert update_res.status_code == 200
    info_data = update_res.json()
    assert info_data["auto_redirect"] is True
    assert info_data["website_url"] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    # 3. Public get endpoint returns auto_redirect correctly
    client.cookies.clear()
    pub_res = await client.get(f"/api/v1/public-info/{uid}")
    assert pub_res.status_code == 200
    assert pub_res.json()["auto_redirect"] is True


@pytest.mark.asyncio
async def test_pdf_attachment_upload_and_inline_retrieval(client: AsyncClient):
    """Test uploading a PDF document, retrieving it inline, and rejecting invalid files."""
    # 1. Register owner and image
    reg = await client.post("/api/v1/auth/register", json={
        "email": "pdf_owner@domain.com",
        "password": "Password123!",
        "full_name": "PDF Owner",
        "role": "owner"
    })
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    img_res = await client.post(
        "/api/v1/images/register",
        files={"file": ("doc.png", create_test_image(), "image/png")},
        data={"title": "PDF Key Asset"},
        headers=headers,
    )
    uid = img_res.json()["public_image_uid"]

    # 2. Upload invalid non-PDF file
    invalid_res = await client.post(
        f"/api/v1/public-info/{uid}/pdf",
        files={"file": ("fake.pdf", b"This is not a real PDF file.", "application/pdf")},
        headers=headers,
    )
    assert invalid_res.status_code == 400
    assert "magic header" in invalid_res.json()["detail"].lower()

    # 3. Upload valid PDF
    pdf_bytes = create_test_pdf()
    valid_res = await client.post(
        f"/api/v1/public-info/{uid}/pdf",
        files={"file": ("instruction_manual.pdf", pdf_bytes, "application/pdf")},
        headers=headers,
    )
    assert valid_res.status_code == 201
    payload = valid_res.json()
    assert payload["has_pdf"] is True
    assert payload["pdf_original_name"] == "instruction_manual.pdf"
    assert f"/api/v1/public-info/{uid}/pdf" in payload["pdf_url"]

    # 4. Fetch PDF inline
    client.cookies.clear()
    get_pdf_res = await client.get(f"/api/v1/public-info/{uid}/pdf")
    assert get_pdf_res.status_code == 200
    assert get_pdf_res.headers["content-type"] == "application/pdf"
    assert "inline" in get_pdf_res.headers.get("content-disposition", "")
    assert get_pdf_res.content == pdf_bytes


@pytest.mark.asyncio
async def test_permanent_deletion_cleans_db_and_storage(client: AsyncClient):
    """Test that DELETE /api/v1/images/{uid} removes DB records and storage files."""
    # 1. Register owner and image
    reg = await client.post("/api/v1/auth/register", json={
        "email": "delete_owner@domain.com",
        "password": "Password123!",
        "full_name": "Delete Owner",
        "role": "owner"
    })
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    img_res = await client.post(
        "/api/v1/images/register",
        files={"file": ("to_delete.png", create_test_image(), "image/png")},
        data={"title": "Asset to Delete"},
        headers=headers,
    )
    uid = img_res.json()["public_image_uid"]

    # 2. Attach a PDF
    await client.post(
        f"/api/v1/public-info/{uid}/pdf",
        files={"file": ("spec.pdf", create_test_pdf(), "application/pdf")},
        headers=headers,
    )

    # Verify download works before delete
    client.cookies.clear()
    dl_before = await client.get(f"/api/v1/images/{uid}/download")
    assert dl_before.status_code == 200

    # 3. Non-owner attempt to delete -> 403 Forbidden
    reg_other = await client.post("/api/v1/auth/register", json={
        "email": "intruder@domain.com",
        "password": "Password123!",
        "full_name": "Intruder User",
        "role": "owner"
    })
    other_token = reg_other.json()["access_token"]
    forbidden_res = await client.delete(
        f"/api/v1/images/{uid}",
        headers={"Authorization": f"Bearer {other_token}"}
    )
    assert forbidden_res.status_code == 403

    # 4. Owner deletes image permanently
    del_res = await client.delete(f"/api/v1/images/{uid}", headers=headers)
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "success"

    # 5. Verify records and downloads return 404
    check_dl = await client.get(f"/api/v1/images/{uid}/download")
    assert check_dl.status_code == 404

    check_pub = await client.get(f"/api/v1/public-info/{uid}")
    assert check_pub.status_code == 404

    check_pdf = await client.get(f"/api/v1/public-info/{uid}/pdf")
    assert check_pdf.status_code == 404


@pytest.mark.asyncio
async def test_shared_with_me_flow(client: AsyncClient):
    """Test granting access and fetching shared assets via /shared-with-me."""
    # 1. Register owner
    reg_owner = await client.post("/api/v1/auth/register", json={
        "email": "sharer_owner@domain.com",
        "password": "Password123!",
        "full_name": "Sharer Owner",
        "role": "owner"
    })
    owner_token = reg_owner.json()["access_token"]
    owner_headers = {"Authorization": f"Bearer {owner_token}"}

    # 2. Register recipient user
    reg_recipient = await client.post("/api/v1/auth/register", json={
        "email": "recipient_user@domain.com",
        "password": "Password123!",
        "full_name": "Recipient User",
        "role": "viewer"
    })
    recipient_token = reg_recipient.json()["access_token"]
    recipient_headers = {"Authorization": f"Bearer {recipient_token}"}

    # 3. Register 3rd party user
    reg_other = await client.post("/api/v1/auth/register", json={
        "email": "unrelated_user@domain.com",
        "password": "Password123!",
        "full_name": "Unrelated User",
        "role": "viewer"
    })
    other_token = reg_other.json()["access_token"]
    other_headers = {"Authorization": f"Bearer {other_token}"}

    # 4. Owner uploads image
    img_res = await client.post(
        "/api/v1/images/register",
        files={"file": ("shared_asset.png", create_test_image(), "image/png")},
        data={"title": "Shared Confidential Document", "description": "Shared blueprints"},
        headers=owner_headers,
    )
    uid = img_res.json()["public_image_uid"]

    # 5. Before grant: recipient shared-with-me is empty
    empty_res = await client.get("/api/v1/images/shared-with-me", headers=recipient_headers)
    assert empty_res.status_code == 200
    assert empty_res.json() == []

    # 6. Owner grants permission to recipient
    grant_res = await client.post(
        f"/api/v1/permissions/{uid}",
        json={
            "email": "recipient_user@domain.com",
            "access_level": "view_private",
        },
        headers=owner_headers,
    )
    assert grant_res.status_code == 201

    # 7. Recipient fetches shared-with-me -> contains the granted image
    shared_res = await client.get("/api/v1/images/shared-with-me", headers=recipient_headers)
    assert shared_res.status_code == 200
    items = shared_res.json()
    assert len(items) == 1
    assert items[0]["public_image_uid"] == uid
    assert items[0]["title"] == "Shared Confidential Document"
    assert items[0]["access_level"] == "view_private"
    assert items[0]["granted_by_email"] == "sharer_owner@domain.com"

    # 8. Unrelated user still sees empty list
    other_shared_res = await client.get("/api/v1/images/shared-with-me", headers=other_headers)
    assert other_shared_res.status_code == 200
    assert other_shared_res.json() == []
