"""Test health and initial Phase 1 endpoints."""

import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_home_page(client: AsyncClient):
    """Verify that the landing page renders HTML correctly."""
    response = await client.get("/")
    assert response.status_code == 200
    assert "IMAGEKEY" in response.text


@pytest.mark.asyncio
async def test_health_endpoint(client: AsyncClient):
    """Verify that the /api/v1/health API returns valid health JSON schema."""
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["app"] == "IMAGEKEY"
    assert "database" in data
    assert "version" in data


@pytest.mark.asyncio
async def test_root_health_alias(client: AsyncClient):
    """Verify that the /health root alias returns identical valid health JSON."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["app"] == "IMAGEKEY"
    assert "database" in data
    assert data["status"] in ("ok", "degraded")


def test_database_url_normalization():
    """Verify cloud host URL conversions for production and free hosting."""
    from app.core.database import normalize_database_url

    # 1. Standard cloud postgres:// conversion
    render_url = "postgres://user:password@dpg-host.render.com:5432/imagekey_db"
    assert normalize_database_url(render_url) == "postgresql+asyncpg://user:password@dpg-host.render.com:5432/imagekey_db"

    # 2. Standard postgresql:// conversion
    neon_url = "postgresql://user:password@ep-cool.neon.tech/neondb"
    assert normalize_database_url(neon_url) == "postgresql+asyncpg://user:password@ep-cool.neon.tech/neondb"

    # 3. Standard sqlite:// conversion
    sqlite_url = "sqlite:///./data/imagekey.db"
    assert normalize_database_url(sqlite_url) == "sqlite+aiosqlite:///./data/imagekey.db"

    # 4. Graceful default fallback when empty or None
    assert normalize_database_url(None) == "sqlite+aiosqlite:///./data/imagekey.db"
    assert normalize_database_url("") == "sqlite+aiosqlite:///./data/imagekey.db"
    assert normalize_database_url("   ") == "sqlite+aiosqlite:///./data/imagekey.db"
