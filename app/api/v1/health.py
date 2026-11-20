"""Health check and diagnostic endpoints."""

from datetime import datetime, timezone
from fastapi import APIRouter
from app.core.config import settings
from app.core.database import check_db_connection
from app.schemas.health import HealthResponse, DatabaseHealth

router = APIRouter()


@router.get("", response_model=HealthResponse, summary="Comprehensive system health check")
async def get_system_health():
    """Verify application, configuration, and database connectivity."""
    db_result = await check_db_connection()
    db_health = DatabaseHealth(**db_result)

    overall_status = "ok" if db_health.healthy else "degraded"

    return HealthResponse(
        app=settings.APP_NAME,
        status=overall_status,
        version="1.0.0",
        environment=settings.ENVIRONMENT,
        timestamp=datetime.now(timezone.utc),
        database=db_health,
        features={
            "perceptual_hash_pipeline": "configured",
            "opencv_descriptor_matching": "configured",
            "rbac_zero_trust": "enforced",
            "phase": "Phase 1 - Base Architecture Active",
        }
    )
