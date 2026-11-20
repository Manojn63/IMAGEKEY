"""Private Information Vault API Routes."""

import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User, UserRole
from app.models.image import RegisteredImage, ImageStatus
from app.models.information import PrivateInformation
from app.models.permission import ImagePermission, AccessLevel
from app.models.access_log import AccessLog, AuditActionType
from app.schemas.information import PrivateInfoResponse, PrivateInfoUpdateRequest

logger = logging.getLogger(__name__)

router = APIRouter()


def is_permission_active(perm: ImagePermission) -> bool:
    """Check whether a permission record is non-expired."""
    if not perm.expires_at:
        return True
    now_utc = datetime.now(timezone.utc)
    exp = perm.expires_at if perm.expires_at.tzinfo else perm.expires_at.replace(tzinfo=timezone.utc)
    return exp > now_utc


@router.get(
    "/{public_image_uid}",
    response_model=PrivateInfoResponse,
    status_code=status.HTTP_200_OK,
    summary="Access Tier 2 Private Vault (Owner, Admin, or Authorized Viewer)"
)
async def get_private_info(
    public_image_uid: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Zero-Trust Protected Private Vault View:
    1. Authenticate user (HTTP 401 if missing/invalid).
    2. Check authorization:
       - Owner of registered image
       - Platform Administrator
       - User granted active, non-expired ImagePermission
    3. If unauthorized: Record UNAUTHORIZED_ATTEMPT in access_logs and return HTTP 403 Forbidden.
    4. If authorized: Record VIEW_PRIVATE in access_logs and return confidential records.
    """
    stmt = (
        select(RegisteredImage)
        .options(
            joinedload(RegisteredImage.public_info),
            joinedload(RegisteredImage.private_info),
            joinedload(RegisteredImage.company),
        )
        .where(
            RegisteredImage.public_image_uid == public_image_uid,
            RegisteredImage.status == ImageStatus.ACTIVE,
        )
    )
    result = await db.execute(stmt)
    image = result.unique().scalar_one_or_none()

    if not image:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Image with UID '{public_image_uid}' not found in active vault."
        )

    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")[:500]

    # Authorization Check
    authorized = False
    user_access_level = "unauthorized"

    if image.owner_id == current_user.id:
        authorized = True
        user_access_level = "owner"
    elif current_user.role == UserRole.ADMIN:
        authorized = True
        user_access_level = "admin"
    else:
        # Check explicit permission
        perm_stmt = select(ImagePermission).where(
            ImagePermission.image_id == image.id,
            ImagePermission.user_id == current_user.id,
        )
        perm = (await db.execute(perm_stmt)).scalar_one_or_none()
        if perm and is_permission_active(perm):
            authorized = True
            user_access_level = perm.access_level.value

    # Reject unauthorized attempts
    if not authorized:
        audit_entry = AccessLog(
            image_id=image.id,
            user_id=current_user.id,
            action_type=AuditActionType.UNAUTHORIZED_ATTEMPT,
            ip_address=client_ip,
            user_agent=user_agent,
            confidence_score=0.0,
        )
        db.add(audit_entry)
        await db.commit()

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You do not possess authorized credentials or active permission to unlock this private vault."
        )

    # Record authorized private view
    audit_entry = AccessLog(
        image_id=image.id,
        user_id=current_user.id,
        action_type=AuditActionType.VIEW_PRIVATE,
        ip_address=client_ip,
        user_agent=user_agent,
        confidence_score=1.0,
    )
    db.add(audit_entry)
    await db.commit()

    pvt = image.private_info
    pinfo = image.public_info

    return PrivateInfoResponse(
        public_image_uid=image.public_image_uid,
        title=pinfo.title if pinfo else "Registered Optical Key",
        confidential_notes=pvt.confidential_notes if pvt else None,
        internal_data_json=pvt.internal_data_json if pvt else {},
        document_paths_json=pvt.document_paths_json if pvt else [],
        user_access_level=user_access_level,
        created_at=pvt.created_at if pvt else None,
        updated_at=pvt.updated_at if pvt else None,
    )


@router.put(
    "/{public_image_uid}",
    response_model=PrivateInfoResponse,
    status_code=status.HTTP_200_OK,
    summary="Update Tier 2 Private Vault contents (Owner, Admin, or EDIT permission)"
)
async def update_private_info(
    public_image_uid: str,
    payload: PrivateInfoUpdateRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Update Private Vault records:
    - Allowed ONLY for Image Owner, Administrator, or a user with active AccessLevel.EDIT permission.
    - All other users receive HTTP 403 Forbidden and are logged under UNAUTHORIZED_ATTEMPT.
    """
    stmt = (
        select(RegisteredImage)
        .options(
            joinedload(RegisteredImage.public_info),
            joinedload(RegisteredImage.private_info),
        )
        .where(RegisteredImage.public_image_uid == public_image_uid)
    )
    result = await db.execute(stmt)
    image = result.unique().scalar_one_or_none()

    if not image:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Image with UID '{public_image_uid}' not found."
        )

    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")[:500]

    # Authorization Check
    can_edit = False
    user_access_level = "unauthorized"

    if image.owner_id == current_user.id:
        can_edit = True
        user_access_level = "owner"
    elif current_user.role == UserRole.ADMIN:
        can_edit = True
        user_access_level = "admin"
    else:
        perm_stmt = select(ImagePermission).where(
            ImagePermission.image_id == image.id,
            ImagePermission.user_id == current_user.id,
            ImagePermission.access_level == AccessLevel.EDIT,
        )
        perm = (await db.execute(perm_stmt)).scalar_one_or_none()
        if perm and is_permission_active(perm):
            can_edit = True
            user_access_level = "edit"

    if not can_edit:
        audit_entry = AccessLog(
            image_id=image.id,
            user_id=current_user.id,
            action_type=AuditActionType.UNAUTHORIZED_ATTEMPT,
            ip_address=client_ip,
            user_agent=user_agent,
            confidence_score=0.0,
        )
        db.add(audit_entry)
        await db.commit()

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You do not have permission to modify this private vault."
        )

    pvt = image.private_info
    if not pvt:
        pvt = PrivateInformation(
            image_id=image.id,
            confidential_notes=payload.confidential_notes,
            internal_data_json=payload.internal_data_json or {},
            document_paths_json=payload.document_paths_json or [],
        )
        db.add(pvt)
    else:
        pvt.confidential_notes = payload.confidential_notes
        pvt.internal_data_json = payload.internal_data_json or {}
        pvt.document_paths_json = payload.document_paths_json or []

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
    await db.refresh(pvt)

    pinfo = image.public_info

    return PrivateInfoResponse(
        public_image_uid=image.public_image_uid,
        title=pinfo.title if pinfo else "Registered Optical Key",
        confidential_notes=pvt.confidential_notes,
        internal_data_json=pvt.internal_data_json,
        document_paths_json=pvt.document_paths_json,
        user_access_level=user_access_level,
        created_at=pvt.created_at,
        updated_at=pvt.updated_at,
    )
