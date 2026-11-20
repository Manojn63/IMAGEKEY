"""Granular Access Permission Management API Routes."""

import logging
import uuid
from datetime import datetime, timezone
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User, UserRole
from app.models.image import RegisteredImage
from app.models.permission import ImagePermission
from app.models.access_log import AccessLog, AuditActionType
from app.schemas.permission import PermissionGrantRequest, PermissionItemResponse

logger = logging.getLogger(__name__)

router = APIRouter()


def check_is_expired(dt: datetime | None) -> bool:
    if not dt:
        return False
    now_utc = datetime.now(timezone.utc)
    exp = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return exp <= now_utc


@router.get(
    "/{public_image_uid}",
    response_model=List[PermissionItemResponse],
    summary="List all granted access permissions for an image (Owner or Admin only)"
)
async def list_permissions(
    public_image_uid: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List granted viewer/editor access permissions for the target registered image."""
    stmt = select(RegisteredImage).where(RegisteredImage.public_image_uid == public_image_uid)
    image = (await db.execute(stmt)).scalar_one_or_none()

    if not image:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Image with UID '{public_image_uid}' not found."
        )

    if image.owner_id != current_user.id and current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Only the image owner or an administrator can manage permissions."
        )

    perms_stmt = (
        select(ImagePermission)
        .options(joinedload(ImagePermission.user))
        .where(ImagePermission.image_id == image.id)
        .order_by(ImagePermission.created_at.desc())
    )
    result = await db.execute(perms_stmt)
    perms = result.scalars().all()

    items = []
    for p in perms:
        items.append(
            PermissionItemResponse(
                id=p.id,
                user_id=p.user_id,
                user_email=p.user.email,
                user_full_name=p.user.full_name,
                access_level=p.access_level.value,
                granted_by=p.granted_by,
                expires_at=p.expires_at,
                is_expired=check_is_expired(p.expires_at),
                created_at=p.created_at,
            )
        )
    return items


@router.post(
    "/{public_image_uid}",
    response_model=PermissionItemResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Grant or update permission for a user by email (Owner or Admin only)"
)
async def grant_permission(
    public_image_uid: str,
    payload: PermissionGrantRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Grant or update viewer/editor permission to another user by email."""
    stmt = select(RegisteredImage).where(RegisteredImage.public_image_uid == public_image_uid)
    image = (await db.execute(stmt)).scalar_one_or_none()

    if not image:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Image with UID '{public_image_uid}' not found."
        )

    if image.owner_id != current_user.id and current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Only the image owner or an administrator can grant permissions."
        )

    # Find target user by email
    target_stmt = select(User).where(User.email == payload.email.lower().strip())
    target_user = (await db.execute(target_stmt)).scalar_one_or_none()

    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with email '{payload.email}' not found."
        )

    if target_user.id == image.owner_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot grant permission to the owner of the image."
        )

    # Check for existing permission
    existing_stmt = select(ImagePermission).where(
        ImagePermission.image_id == image.id,
        ImagePermission.user_id == target_user.id,
    )
    perm = (await db.execute(existing_stmt)).scalar_one_or_none()

    if perm:
        perm.access_level = payload.access_level
        perm.expires_at = payload.expires_at
        perm.granted_by = current_user.id
    else:
        perm = ImagePermission(
            image_id=image.id,
            user_id=target_user.id,
            access_level=payload.access_level,
            granted_by=current_user.id,
            expires_at=payload.expires_at,
        )
        db.add(perm)

    # Audit logging
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")[:500]

    audit_entry = AccessLog(
        image_id=image.id,
        user_id=current_user.id,
        action_type=AuditActionType.PERMISSION_CHANGE,
        ip_address=client_ip,
        user_agent=user_agent,
        confidence_score=1.0,
    )
    db.add(audit_entry)

    await db.commit()
    await db.refresh(perm)

    return PermissionItemResponse(
        id=perm.id,
        user_id=target_user.id,
        user_email=target_user.email,
        user_full_name=target_user.full_name,
        access_level=perm.access_level.value,
        granted_by=perm.granted_by,
        expires_at=perm.expires_at,
        is_expired=check_is_expired(perm.expires_at),
        created_at=perm.created_at,
    )


@router.delete(
    "/{public_image_uid}/{user_id}",
    status_code=status.HTTP_200_OK,
    summary="Revoke permission for a user (Owner or Admin only)"
)
async def revoke_permission(
    public_image_uid: str,
    user_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Immediately revoke access permission for a given user."""
    stmt = select(RegisteredImage).where(RegisteredImage.public_image_uid == public_image_uid)
    image = (await db.execute(stmt)).scalar_one_or_none()

    if not image:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Image with UID '{public_image_uid}' not found."
        )

    if image.owner_id != current_user.id and current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Only the image owner or an administrator can revoke permissions."
        )

    perm_stmt = select(ImagePermission).where(
        ImagePermission.image_id == image.id,
        ImagePermission.user_id == user_id,
    )
    perm = (await db.execute(perm_stmt)).scalar_one_or_none()

    if not perm:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Permission record not found for this user."
        )

    await db.delete(perm)

    # Audit logging
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")[:500]

    audit_entry = AccessLog(
        image_id=image.id,
        user_id=current_user.id,
        action_type=AuditActionType.PERMISSION_CHANGE,
        ip_address=client_ip,
        user_agent=user_agent,
        confidence_score=1.0,
    )
    db.add(audit_entry)

    await db.commit()

    return {"message": "Permission successfully revoked."}
