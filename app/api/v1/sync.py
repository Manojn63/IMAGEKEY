"""Sync status endpoints for client data synchronization."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.sync import SyncStatusResponse
from app.services.sync import compute_sync_status

router = APIRouter()


@router.get(
    "/sync-status",
    response_model=SyncStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current data and version sync status"
)
async def get_sync_status(db: AsyncSession = Depends(get_db)):
    """
    Returns the latest version hash and timestamp of database state.
    Mobile/PWA clients poll this endpoint to automatically detect modifications
    and refresh active UI views without serving stale cached content.
    """
    result = await compute_sync_status(db)
    return SyncStatusResponse(**result)
