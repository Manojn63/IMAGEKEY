"""API v1 router bundle."""

from fastapi import APIRouter
from app.api.v1.health import router as health_router
from app.api.v1.auth import router as auth_router
from app.api.v1.images import router as images_router
from app.api.v1.scanner import router as scanner_router
from app.api.v1.public_info import router as public_info_router
from app.api.v1.private_info import router as private_info_router
from app.api.v1.permissions import router as permissions_router
from app.api.v1.admin import router as admin_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(health_router, prefix="/health", tags=["Health"])
api_v1_router.include_router(auth_router, prefix="/auth", tags=["Authentication"])
api_v1_router.include_router(images_router, prefix="/images", tags=["Images"])
api_v1_router.include_router(scanner_router, prefix="/scanner", tags=["Scanner"])
api_v1_router.include_router(public_info_router, prefix="/public-info", tags=["Public Information"])
api_v1_router.include_router(private_info_router, prefix="/private-info", tags=["Private Vault"])
api_v1_router.include_router(permissions_router, prefix="/permissions", tags=["Permissions"])
api_v1_router.include_router(admin_router, prefix="/admin", tags=["Admin"])

__all__ = ["api_v1_router"]
