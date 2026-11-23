"""IMAGEKEY - Main FastAPI Application Entrypoint."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from app.core.limiter import limiter
from app.core.config import settings
from app.core.database import check_db_connection, init_db, get_db
import app.models  # Ensures all 7 ORM models are registered
from app.api.v1 import api_v1_router
from app.api.v1.health import get_system_health
from app.schemas.health import HealthResponse
from app.schemas.sync import SyncStatusResponse
from app.services.sync import compute_sync_status

# Configure logging
logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("imagekey")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle events: startup and shutdown."""
    logger.info("Initializing %s in %s environment...", settings.APP_NAME, settings.ENVIRONMENT)

    # Ensure data and upload directories exist
    Path("./data").mkdir(parents=True, exist_ok=True)
    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    (settings.UPLOAD_DIR / "pdfs").mkdir(parents=True, exist_ok=True)

    # Test database connectivity
    db_check = await check_db_connection()
    if db_check.get("healthy"):
        logger.info("Database connectivity verified successfully.")
        try:
            await init_db()
            logger.info("Database schema synchronized successfully.")
        except Exception as e:
            logger.warning("Database schema auto-sync note: %s", e)
    else:
        logger.warning(
            "Database not currently accessible (%s). App starting in standalone mode.",
            db_check.get("error", "No connection")
        )

    yield

    logger.info("Shutting down %s...", settings.APP_NAME)


# Initialize FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    description="Secure image-based tiered information sharing and recognition platform.",
    version="1.0.0",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan,
)

# Rate Limiter setup
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# HTTP Security Headers Middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Enforce strict defensive HTTP headers and prevent stale caches on dynamic responses."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(self)"

    # Prevent stale caching on dynamic API responses, sync endpoints, and stateful views
    path = request.url.path
    if path.startswith("/api/") or path.startswith("/api") or path in ("/health", "/demo/upi"):
        if "Cache-Control" not in response.headers or response.headers["Cache-Control"] == "no-cache":
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"

    return response

# CORS middleware (Explicit origins required when allow_credentials=True)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8000", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files mounting
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Templates engine
templates_dir = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))

# Service Worker route for Android APK / PWA installability
@app.get("/sw.js", response_class=FileResponse, include_in_schema=False)
async def service_worker():
    """Serve Service Worker from root domain scope for complete PWA/APK control."""
    sw_file = Path(__file__).parent / "static" / "sw.js"
    return FileResponse(
        path=str(sw_file),
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache"}
    )

# Root health check alias
@app.get("/health", response_model=HealthResponse, summary="Root Health Check Alias")
async def root_health_alias():
    """Consistent root-level alias for /api/v1/health."""
    return await get_system_health()

# Root sync status alias
@app.get("/api/sync-status", response_model=SyncStatusResponse, summary="Root Sync Status")
async def root_sync_status(db: AsyncSession = Depends(get_db)):
    """Top-level sync status endpoint for mobile and frontend auto-polling."""
    result = await compute_sync_status(db)
    return SyncStatusResponse(**result)

# Mount API Routers
app.include_router(api_v1_router)


# Frontend Web Routes
@app.get("/", response_class=HTMLResponse, summary="Landing Page")
async def home_page(request: Request):
    """Render the main landing page with system diagnostics."""
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "app_name": settings.APP_NAME,
            "environment": settings.ENVIRONMENT,
            "debug": settings.DEBUG,
        }
    )


@app.get("/auth/login", response_class=HTMLResponse, summary="Login Page")
@app.get("/auth/register", response_class=HTMLResponse, summary="Register Page")
async def auth_page(request: Request):
    """Render the login and registration page."""
    return templates.TemplateResponse(
        request=request,
        name="auth/auth.html",
        context={
            "app_name": settings.APP_NAME,
            "environment": settings.ENVIRONMENT,
        }
    )


@app.get("/dashboard", response_class=HTMLResponse, summary="User Dashboard (Phase 6)")
async def dashboard_page(request: Request):
    """Render the authenticated User Dashboard view."""
    return templates.TemplateResponse(
        request=request,
        name="dashboard/index.html",
        context={
            "app_name": settings.APP_NAME,
            "environment": settings.ENVIRONMENT,
        }
    )


# Stubs for forthcoming views (Phase 2-7)
@app.get("/scan", response_class=HTMLResponse, summary="Scanner View (Phase 4)")
async def scanner_page(request: Request):
    """Render the Optical Vault live camera scanner and image identifier view."""
    return templates.TemplateResponse(
        request=request,
        name="scanner/scan.html",
        context={
            "app_name": settings.APP_NAME,
            "environment": settings.ENVIRONMENT,
        }
    )


@app.get("/register-image", response_class=HTMLResponse, summary="Register Image (Phase 3)")
async def register_page(request: Request):
    """Render the Image Registration and Hashing View."""
    return templates.TemplateResponse(
        request=request,
        name="images/upload.html",
        context={
            "app_name": settings.APP_NAME,
            "environment": settings.ENVIRONMENT,
        }
    )


@app.get("/public/{public_image_uid}", response_class=HTMLResponse, summary="Public Information View (Phase 5)")
async def public_info_page(request: Request, public_image_uid: str):
    """Render the open Public Information display view."""
    return templates.TemplateResponse(
        request=request,
        name="public/view.html",
        context={
            "app_name": settings.APP_NAME,
            "environment": settings.ENVIRONMENT,
            "public_image_uid": public_image_uid,
        }
    )


@app.get("/images/{public_image_uid}/edit", response_class=HTMLResponse, summary="Image Info Editor (Phase 5+)")
async def edit_image_page(request: Request, public_image_uid: str):
    """Render the Image Vault Editor view."""
    return templates.TemplateResponse(
        request=request,
        name="images/editor.html",
        context={
            "app_name": settings.APP_NAME,
            "environment": settings.ENVIRONMENT,
            "public_image_uid": public_image_uid,
        }
    )


@app.get("/vault/{public_image_uid}", response_class=HTMLResponse, summary="Protected Private Vault View (Phase 6)")
async def private_vault_page(request: Request, public_image_uid: str):
    """Render the protected Tier 2 Private Vault view."""
    return templates.TemplateResponse(
        request=request,
        name="private/vault.html",
        context={
            "app_name": settings.APP_NAME,
            "environment": settings.ENVIRONMENT,
            "public_image_uid": public_image_uid,
        }
    )


@app.get("/images/{public_image_uid}/permissions", response_class=HTMLResponse, summary="Access Permission Manager (Phase 6)")
async def permissions_page(request: Request, public_image_uid: str):
    """Render the Granular Access Permission Manager view."""
    return templates.TemplateResponse(
        request=request,
        name="permissions/manage.html",
        context={
            "app_name": settings.APP_NAME,
            "environment": settings.ENVIRONMENT,
            "public_image_uid": public_image_uid,
        }
    )


@app.get("/admin", response_class=HTMLResponse, summary="Admin Operations Dashboard (Phase 7)")
async def admin_dashboard_page(request: Request):
    """Render the Optical Vault Administrator Dashboard."""
    return templates.TemplateResponse(
        request=request,
        name="admin/index.html",
        context={
            "app_name": settings.APP_NAME,
            "environment": settings.ENVIRONMENT,
        }
    )


@app.get("/demo/upi", response_class=HTMLResponse, summary="In-App Simulated UPI Demo View")
async def upi_demo_page(request: Request):
    """Render the Simulated UPI Payment Demonstration view."""
    return templates.TemplateResponse(
        request=request,
        name="demo/upi.html",
        context={
            "app_name": settings.APP_NAME,
            "environment": settings.ENVIRONMENT,
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
