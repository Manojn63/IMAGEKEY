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
