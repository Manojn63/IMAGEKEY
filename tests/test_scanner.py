"""Automated tests for Image Recognition Engine, Scanner API, and Page 6 UI."""

import io
import pytest
from PIL import Image, ImageDraw
from httpx import AsyncClient
from sqlalchemy import select
from app.models.access_log import AccessLog, AuditActionType


def create_feature_rich_image(size=(200, 200), primary_color=(220, 20, 60)) -> bytes:
    """Generate a test image with distinct geometric features for ORB and pHash detection."""
    img = Image.new("RGB", size, color=(245, 245, 245))
    draw = ImageDraw.Draw(img)
    # Distinct shapes generating robust keypoints
    draw.rectangle([20, 20, 80, 80], fill=primary_color, outline=(0, 0, 0))
    draw.ellipse([100, 20, 180, 100], fill=(20, 100, 220), outline=(0, 0, 0))
    draw.polygon([(40, 110), (100, 180), (20, 180)], fill=(34, 139, 34), outline=(0, 0, 0))
    draw.line([(0, 0), (200, 200)], fill=(0, 0, 0), width=3)
    draw.line([(0, 200), (200, 0)], fill=(128, 0, 128), width=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def create_unrelated_image(size=(200, 200)) -> bytes:
    """Generate an entirely distinct image with non-matching features."""
    img = Image.new("RGB", size, color=(15, 23, 42))
    draw = ImageDraw.Draw(img)
    draw.ellipse([50, 50, 150, 150], fill=(234, 179, 8), outline=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def create_modified_query(original_bytes: bytes, scale=0.85) -> bytes:
    """Generate a scaled and JPEG-compressed version of an original image."""
    orig = Image.open(io.BytesIO(original_bytes))
    new_size = (int(orig.width * scale), int(orig.height * scale))
    resized = orig.resize(new_size, Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    resized.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_exact_image_scan_match(client: AsyncClient, db_session):
    """Test exact image recognition returns VERIFIED_MATCH (>= 85%) and logs success."""
    # 1. Register an image as owner
    reg_user = await client.post("/api/v1/auth/register", json={
        "email": "scannerowner@vault.com",
        "password": "Password123!",
        "full_name": "Scanner Owner",
        "role": "owner"
    })
    token = reg_user.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    original_bytes = create_feature_rich_image()
    files = {"file": ("brand_logo.png", original_bytes, "image/png")}
    data = {"title": "Acme High Security Emblem", "description": "Official company emblem"}

    reg_res = await client.post("/api/v1/images/register", files=files, data=data, headers=headers)
    assert reg_res.status_code == 201
    registered_uid = reg_res.json()["public_image_uid"]

    # 2. Perform anonymous scan with the identical image
    scan_files = {"file": ("query.png", original_bytes, "image/png")}
    scan_res = await client.post("/api/v1/scanner/identify", files=scan_files)
    assert scan_res.status_code == 200
    res_data = scan_res.json()

    # 3. Verify verdict and confidence
    assert res_data["verdict"] == "VERIFIED_MATCH"
    assert res_data["confidence_score"] >= 0.85
    assert res_data["confidence_percentage"] >= 85.0
    assert res_data["match"] is not None
    assert res_data["match"]["public_image_uid"] == registered_uid
    assert res_data["match"]["title"] == "Acme High Security Emblem"
    assert res_data["match"]["description"] == "Official company emblem"

    # 4. Verify audit log entry was created
    audit_stmt = select(AccessLog).where(AccessLog.action_type == AuditActionType.SCAN_SUCCESS)
    logs = (await db_session.execute(audit_stmt)).scalars().all()
    assert len(logs) >= 1
    assert logs[-1].confidence_score >= 0.85


@pytest.mark.asyncio
async def test_scaled_compressed_image_scan_match(client: AsyncClient):
    """Test that resized and compressed query image still matches successfully."""
    # Register image
    reg_user = await client.post("/api/v1/auth/register", json={
        "email": "scaleowner@vault.com",
        "password": "Password123!",
        "full_name": "Scale Tester",
        "role": "owner"
    })
    token = reg_user.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    original_bytes = create_feature_rich_image()
    files = {"file": ("original.png", original_bytes, "image/png")}
    data = {"title": "Scale Robust Graphic"}

    reg_res = await client.post("/api/v1/images/register", files=files, data=data, headers=headers)
    registered_uid = reg_res.json()["public_image_uid"]

    # Scale down by 15% and re-encode to JPEG
    query_bytes = create_modified_query(original_bytes, scale=0.85)
    scan_files = {"file": ("scaled_query.jpg", query_bytes, "image/jpeg")}
    scan_res = await client.post("/api/v1/scanner/identify", files=scan_files)
    assert scan_res.status_code == 200
    res_data = scan_res.json()

    # Should match with confidence >= 65% (VERIFIED_MATCH or UNCERTAIN)
    assert res_data["verdict"] in ("VERIFIED_MATCH", "UNCERTAIN")
    assert res_data["confidence_score"] >= 0.65
    if res_data["verdict"] == "VERIFIED_MATCH":
        assert res_data["match"]["public_image_uid"] == registered_uid


@pytest.mark.asyncio
async def test_unregistered_image_returns_no_match(client: AsyncClient, db_session):
    """Test that scanning an unregistered/distinct image returns NO_MATCH (< 65%)."""
    # 1. Register a distinct image
    reg_user = await client.post("/api/v1/auth/register", json={
        "email": "otherowner@vault.com",
        "password": "Password123!",
        "full_name": "Other Owner",
        "role": "owner"
    })
    token = reg_user.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    reg_img = create_feature_rich_image()
    files = {"file": ("registered.png", reg_img, "image/png")}
    data = {"title": "Registered Image"}
    await client.post("/api/v1/images/register", files=files, data=data, headers=headers)

    # 2. Query with completely different image
    unrelated_bytes = create_unrelated_image()
    scan_files = {"file": ("unrelated.png", unrelated_bytes, "image/png")}
    scan_res = await client.post("/api/v1/scanner/identify", files=scan_files)
    assert scan_res.status_code == 200
    res_data = scan_res.json()

    # 3. Assert NO_MATCH and match is None
    assert res_data["verdict"] == "NO_MATCH"
    assert res_data["confidence_score"] < 0.65
    assert res_data["match"] is None
    assert "No matching" in res_data["message"]

    # 4. Verify access log recorded failure
    audit_stmt = select(AccessLog).where(AccessLog.action_type == AuditActionType.SCAN_FAIL)
    logs = (await db_session.execute(audit_stmt)).scalars().all()
    assert len(logs) >= 1


@pytest.mark.asyncio
async def test_empty_database_scan_returns_no_match(client: AsyncClient):
    """Test scan behavior when no images exist in database."""
    query_bytes = create_feature_rich_image()
    scan_files = {"file": ("query.png", query_bytes, "image/png")}
    scan_res = await client.post("/api/v1/scanner/identify", files=scan_files)
    assert scan_res.status_code == 200
    res_data = scan_res.json()

    assert res_data["verdict"] == "NO_MATCH"
    assert res_data["confidence_score"] == 0.0
    assert res_data["match"] is None


@pytest.mark.asyncio
async def test_zero_trust_payload_isolation(client: AsyncClient):
    """Verify that private information is NEVER returned or present in scan response."""
    reg_user = await client.post("/api/v1/auth/register", json={
        "email": "confidentialowner@vault.com",
        "password": "Password123!",
        "full_name": "Confidential Owner",
        "role": "owner"
    })
    token = reg_user.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    img_bytes = create_feature_rich_image()
    files = {"file": ("vault_image.png", img_bytes, "image/png")}
    data = {"title": "Vault Protected Image"}
    await client.post("/api/v1/images/register", files=files, data=data, headers=headers)

    scan_files = {"file": ("scan.png", img_bytes, "image/png")}
    scan_res = await client.post("/api/v1/scanner/identify", files=scan_files)
    assert scan_res.status_code == 200
    raw_json = scan_res.json()

    # Assert private fields are strictly nonexistent in payload
    assert "confidential_notes" not in str(raw_json)
    assert "internal_data" not in str(raw_json)
    assert "document_paths" not in str(raw_json)


@pytest.mark.asyncio
async def test_scanner_invalid_and_oversized_files(client: AsyncClient):
    """Test bad requests are handled properly with status codes 400 and 413."""
    # Empty file
    empty_file = {"file": ("empty.png", b"", "image/png")}
    res = await client.post("/api/v1/scanner/identify", files=empty_file)
    assert res.status_code == 400

    # Non-image file
    invalid_file = {"file": ("script.sh", b"#!/bin/bash\necho hello", "image/png")}
    res = await client.post("/api/v1/scanner/identify", files=invalid_file)
    assert res.status_code == 400

    # Oversized file
    huge_bytes = b"0" * (5 * 1024 * 1024 + 1024)
    huge_file = {"file": ("huge.jpg", huge_bytes, "image/jpeg")}
    res = await client.post("/api/v1/scanner/identify", files=huge_file)
    assert res.status_code == 413


@pytest.mark.asyncio
async def test_scanner_html_page_rendered(client: AsyncClient):
    """Verify that the Page 6 live scanner HTML template renders properly."""
    res = await client.get("/scan")
    assert res.status_code == 200
    assert "Optical Vault Scanner" in res.text
    assert "Live Camera" in res.text
    assert "Upload Image" in res.text
    assert "hud-laser" in res.text
    assert "viewfinder-wrapper" in res.text
    assert "Zero-Trust Optical Security" in res.text
