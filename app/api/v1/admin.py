"""Admin Dashboard, Audit Log Viewing & Platform Moderation API Routes."""

import logging
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from sqlalchemy import select, func
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_role
from app.models.user import User, UserRole
from app.models.image import RegisteredImage, ImageStatus
from app.models.access_log import AccessLog, AuditActionType
from app.schemas.admin import (
    AdminOverviewResponse,
    AdminUserItem,
    AdminUserStatusUpdate,
    AdminImageItem,
    AdminImageStatusUpdate,
    AdminLogItem,
    AdminLogsResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_role([UserRole.ADMIN]))])


@router.get(
    "/overview",
    response_model=AdminOverviewResponse,
    summary="Get platform-wide KPI metrics (Admin only)"
)
async def get_admin_overview(
    db: AsyncSession = Depends(get_db),
):
    """Retrieve global platform statistics for the Admin Dashboard."""
    # User counts
    users_count = (await db.execute(select(func.count(User.id)))).scalar() or 0

    # Image counts
    total_imgs = (await db.execute(select(func.count(RegisteredImage.id)))).scalar() or 0
    active_imgs = (await db.execute(
        select(func.count(RegisteredImage.id)).where(RegisteredImage.status == ImageStatus.ACTIVE)
    )).scalar() or 0
    suspended_imgs = (await db.execute(
        select(func.count(RegisteredImage.id)).where(RegisteredImage.status == ImageStatus.SUSPENDED)
    )).scalar() or 0

    # Log metrics
    total_scans = (await db.execute(
        select(func.count(AccessLog.id)).where(
            AccessLog.action_type.in_([AuditActionType.SCAN_SUCCESS, AuditActionType.SCAN_FAIL])
        )
    )).scalar() or 0

    unauthorized_attempts = (await db.execute(
        select(func.count(AccessLog.id)).where(
            AccessLog.action_type == AuditActionType.UNAUTHORIZED_ATTEMPT
        )
    )).scalar() or 0

    return AdminOverviewResponse(
        total_users=users_count,
        total_images=total_imgs,
        active_images=active_imgs,
        suspended_images=suspended_imgs,
        total_scans=total_scans,
        unauthorized_attempts=unauthorized_attempts,
    )


@router.get(
    "/users",
    response_model=List[AdminUserItem],
    summary="List all registered platform users (Admin only)"
)
async def list_admin_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    """List platform users ordered by registration date."""
    stmt = select(User).order_by(User.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    users = result.scalars().all()

    return [
        AdminUserItem(
            id=u.id,
            email=u.email,
            full_name=u.full_name,
            role=u.role.value,
            is_active=u.is_active,
            created_at=u.created_at,
        )
        for u in users
    ]


@router.patch(
    "/users/{user_id}/status",
    response_model=AdminUserItem,
    summary="Toggle user active status (Admin only)"
)
async def update_user_status(
    user_id: uuid.UUID,
    payload: AdminUserStatusUpdate,
    request: Request,
    current_admin: User = Depends(require_role([UserRole.ADMIN])),
    db: AsyncSession = Depends(get_db),
):
    """Suspend or activate a user account (prevents admins from suspending themselves)."""
    if current_admin.id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Administrators cannot suspend their own account."
        )

    stmt = select(User).where(User.id == user_id)
    user = (await db.execute(stmt)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    user.is_active = payload.is_active

    # Audit log entry
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")[:500]
    audit_entry = AccessLog(
        image_id=None,
        user_id=current_admin.id,
        action_type=AuditActionType.PERMISSION_CHANGE,
        ip_address=client_ip,
        user_agent=user_agent,
        confidence_score=1.0,
    )
    db.add(audit_entry)

    await db.commit()
    await db.refresh(user)

    return AdminUserItem(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role.value,
        is_active=user.is_active,
        created_at=user.created_at,
    )


@router.get(
    "/images",
    response_model=List[AdminImageItem],
    summary="List all registered images across the platform (Admin only)"
)
async def list_admin_images(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    """List all registered images with owner email and public metadata."""
    stmt = (
        select(RegisteredImage)
        .options(
            joinedload(RegisteredImage.owner),
            joinedload(RegisteredImage.company),
            joinedload(RegisteredImage.public_info),
        )
        .order_by(RegisteredImage.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    images = result.unique().scalars().all()

    items = []
    for img in images:
        title = img.public_info.title if img.public_info else "Registered Optical Key"
        comp_name = img.company.name if img.company else None
        items.append(
            AdminImageItem(
                id=img.id,
                public_image_uid=img.public_image_uid,
                title=title,
                owner_email=img.owner.email,
                company_name=comp_name,
                status=img.status.value,
                phash=img.phash,
                created_at=img.created_at,
            )
        )
    return items


@router.patch(
    "/images/{public_image_uid}/status",
    response_model=AdminImageItem,
    summary="Toggle image status between active and suspended (Admin only)"
)
async def update_image_status(
    public_image_uid: str,
    payload: AdminImageStatusUpdate,
    request: Request,
    current_admin: User = Depends(require_role([UserRole.ADMIN])),
    db: AsyncSession = Depends(get_db),
):
    """Suspend or re-activate an image in the vault."""
    stmt = (
        select(RegisteredImage)
        .options(
            joinedload(RegisteredImage.owner),
            joinedload(RegisteredImage.company),
            joinedload(RegisteredImage.public_info),
        )
        .where(RegisteredImage.public_image_uid == public_image_uid)
    )
    image = (await db.execute(stmt)).unique().scalar_one_or_none()
    if not image:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found.")

    image.status = payload.status

    # Audit log
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")[:500]
    audit_entry = AccessLog(
        image_id=image.id,
        user_id=current_admin.id,
        action_type=AuditActionType.PERMISSION_CHANGE,
        ip_address=client_ip,
        user_agent=user_agent,
        confidence_score=1.0,
    )
    db.add(audit_entry)

    await db.commit()
    await db.refresh(image)

    title = image.public_info.title if image.public_info else "Registered Optical Key"
    comp_name = image.company.name if image.company else None

    return AdminImageItem(
        id=image.id,
        public_image_uid=image.public_image_uid,
        title=title,
        owner_email=image.owner.email,
        company_name=comp_name,
        status=image.status.value,
        phash=image.phash,
        created_at=image.created_at,
    )


@router.get(
    "/logs",
    response_model=AdminLogsResponse,
    summary="Get paginated and filterable audit logs (Admin only)"
)
async def list_admin_logs(
    action_type: Optional[AuditActionType] = Query(None, description="Filter by audit action"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """View platform audit event stream."""
    stmt = (
        select(AccessLog)
        .options(
            joinedload(AccessLog.image),
            joinedload(AccessLog.user),
        )
    )
    count_stmt = select(func.count(AccessLog.id))

    if action_type:
        stmt = stmt.where(AccessLog.action_type == action_type)
        count_stmt = count_stmt.where(AccessLog.action_type == action_type)

    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = stmt.order_by(AccessLog.timestamp.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    logs = result.scalars().all()

    items = []
    for lg in logs:
        img_uid = lg.image.public_image_uid if lg.image else None
        user_email = lg.user.email if lg.user else None
        items.append(
            AdminLogItem(
                id=lg.id,
                image_uid=img_uid,
                user_email=user_email,
                action_type=lg.action_type.value,
                ip_address=lg.ip_address,
                user_agent=lg.user_agent,
                confidence_score=lg.confidence_score,
                timestamp=lg.timestamp,
            )
        )

    return AdminLogsResponse(total=total, logs=items)
