"""Tests for CORS behavior, Static Assets, and Frontend Route Status."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_cors_allowed_origin(client: AsyncClient):
    """Test that allowed origin receives correct CORS response headers."""
    res = await client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:8000",
            "Access-Control-Request-Method": "GET"
        }
    )
    assert res.status_code == 200
    assert res.headers.get("access-control-allow-origin") == "http://localhost:8000"
    assert res.headers.get("access-control-allow-credentials") == "true"


@pytest.mark.asyncio
async def test_cors_disallowed_origin(client: AsyncClient):
    """Test that unauthorized origin does not receive Access-Control-Allow-Origin header."""
    res = await client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://unauthorized-domain.com",
            "Access-Control-Request-Method": "GET"
        }
    )
    assert res.headers.get("access-control-allow-origin") is None


@pytest.mark.asyncio
async def test_static_assets_served(client: AsyncClient):
    """Verify that CSS and JS static assets are accessible."""
    css_res = await client.get("/static/css/theme.css")
    assert css_res.status_code == 200
    assert "Optical Vault" in css_res.text or "--color-primary" in css_res.text

    js_res = await client.get("/static/js/theme.js")
    assert js_res.status_code == 200
    assert "IMAGEKEY_THEME" in js_res.text or "imagekey_theme" in js_res.text


@pytest.mark.asyncio
async def test_auth_pages_rendered(client: AsyncClient):
    """Verify login and register views render HTML with Optical Vault styling."""
    login_res = await client.get("/auth/login")
    assert login_res.status_code == 200
    assert "Optical Vault Access" in login_res.text
    assert "Sign In" in login_res.text

    reg_res = await client.get("/auth/register")
    assert reg_res.status_code == 200
    assert "Optical Vault Access" in reg_res.text
    assert "Create Account" in reg_res.text


@pytest.mark.asyncio
async def test_pwa_manifest_and_mobile_nav(client: AsyncClient):
    """Verify that PWA manifest.json is accessible and mobile bottom nav exists in base templates."""
    # 1. Check manifest.json
    manifest_res = await client.get("/static/manifest.json")
    assert manifest_res.status_code == 200
    manifest_json = manifest_res.json()
    assert manifest_json["short_name"] == "IMAGEKEY"
    assert manifest_json["display"] == "standalone"
    assert manifest_json["theme_color"] in ["#1E40AF", "#0A0D14"]

    # 2. Check home page renders mobile meta and bottom nav bar
    home_res = await client.get("/")
    assert home_res.status_code == 200
    assert 'rel="manifest"' in home_res.text
    assert 'apple-mobile-web-app-capable' in home_res.text
    assert 'mobile-bottom-nav' in home_res.text
    assert 'Home' in home_res.text
    assert 'Scan' in home_res.text
    assert 'Upload' in home_res.text
    # 3. Check service worker and brand logo
    sw_res = await client.get("/sw.js")
    assert sw_res.status_code == 200
    assert "imagekey" in sw_res.text.lower()

    logo_res = await client.get("/static/img/logo.png")
    assert logo_res.status_code == 200
    assert len(logo_res.content) > 0

