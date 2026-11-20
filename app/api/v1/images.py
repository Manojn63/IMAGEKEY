"""Image Registration and Management API Routes."""

import os
import uuid
import logging
from datetime import datetime, timezone
from typing import List, Optional
from pathlib import Path
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, status, Request
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user, require_role
from app.models.user import User, UserRole
from app.models.image import RegisteredImage, ImageStatus
from app.models.information import PublicInformation
from app.models.permission import ImagePermission
from app.models.access_log import AccessLog, AuditActionType
from app.schemas.image import ImageRegisterResponse, MyImageItem, SharedImageItem
from app.services.vision import (
    sanitize_and_strip_exif,
    extract_perceptual_hashes,
    extract_orb_descriptors,
    generate_public_image_uid,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/register",
    response_model=ImageRegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new image with perceptual hash and ORB features"
)
async def register_image(
    request: Request,
    file: UploadFile = File(...),
    title: str = Form(..., min_length=2, max_length=200),
    description: Optional[str] = Form(None, max_length=2000),
    company_id: Optional[uuid.UUID] = Form(None),
    current_user: User = Depends(require_role([UserRole.OWNER, UserRole.ADMIN])),
    db: AsyncSession = Depends(get_db),
):
    """
    Secure Image Upload Pipeline:
    1. Validate size (max 5MB) and MIME type.
    2. Sanitize and strip EXIF metadata via Pillow.
    3. Generate cryptographically unique public_image_uid.
    4. Compute pHash, dHash, and OpenCV ORB feature descriptors.
    5. Save sanitized image to storage outside public root.
    6. Persist records and record audit log.
    """
    # 1. Read and validate raw bytes size
    raw_bytes = await file.read()
    if len(raw_bytes) > settings.MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File exceeds maximum allowed size of {settings.MAX_FILE_SIZE_BYTES // (1024*1024)}MB."
        )

    if len(raw_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty."
        )

    # 2. Sanitize and strip EXIF
    try:
        clean_pil, ext = sanitize_and_strip_exif(raw_bytes)
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve)
        )

    # 3. Generate unique random public_image_uid
    public_uid = ""
    for _ in range(5):
        candidate_uid = generate_public_image_uid(length=8)
        existing = await db.execute(
            select(RegisteredImage).where(RegisteredImage.public_image_uid == candidate_uid)
        )
        if not existing.scalar_one_or_none():
            public_uid = candidate_uid
            break

    if not public_uid:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not generate unique image identifier."
        )

    # 4. Save sanitized file outside public web root
    storage_filename = f"{uuid.uuid4().hex}.{ext}"
    storage_path = settings.UPLOAD_DIR / storage_filename
    clean_pil.save(storage_path, format="PNG" if ext == "png" else "JPEG", quality=95)

    # 5. Extract Computer Vision features
    phash_str, dhash_str = extract_perceptual_hashes(clean_pil)
    orb_bytes = extract_orb_descriptors(clean_pil, max_features=500)

    # 6. Database record creation
    new_image = RegisteredImage(
        public_image_uid=public_uid,
        owner_id=current_user.id,
        company_id=company_id,
        file_path=str(storage_path),
        phash=phash_str,
        dhash=dhash_str,
        orb_descriptors=orb_bytes,
        status=ImageStatus.ACTIVE,
    )
    db.add(new_image)
    await db.flush()

    # Link initial Public Information
    public_info = PublicInformation(
        image_id=new_image.id,
        title=title.strip(),
        description=description.strip() if description else None,
    )
    db.add(public_info)

    # 7. Audit log creation
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")[:500]
    audit_entry = AccessLog(
        image_id=new_image.id,
        user_id=current_user.id,
        action_type=AuditActionType.PERMISSION_CHANGE,
        ip_address=client_ip,
        user_agent=user_agent,
        confidence_score=1.0,
    )
    db.add(audit_entry)

    await db.commit()
    await db.refresh(new_image)

    return ImageRegisterResponse(
        id=new_image.id,
        public_image_uid=new_image.public_image_uid,
        owner_id=new_image.owner_id,
        company_id=new_image.company_id,
        phash=new_image.phash,
        dhash=new_image.dhash,
        has_orb_descriptors=new_image.orb_descriptors is not None,
        status=new_image.status.value,
        title=public_info.title,
        description=public_info.description,
        created_at=new_image.created_at,
    )


@router.get(
    "/my-images",
    response_model=List[MyImageItem],
    summary="List all images registered by the current user"
)
async def get_my_images(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Fetch images owned by authenticated user joined with their public titles."""
    stmt = (
        select(RegisteredImage, PublicInformation)
        .outerjoin(PublicInformation, RegisteredImage.id == PublicInformation.image_id)
        .where(RegisteredImage.owner_id == current_user.id)
        .order_by(RegisteredImage.created_at.desc())
    )
    results = await db.execute(stmt)
    items = []
    for img, pinfo in results:
        items.append(
            MyImageItem(
                id=img.id,
                public_image_uid=img.public_image_uid,
                title=pinfo.title if pinfo else "Untitled Image",
                description=pinfo.description if pinfo else None,
                phash=img.phash,
                status=img.status.value,
                created_at=img.created_at,
            )
        )
    return items


@router.get(
    "/shared-with-me",
    response_model=List[SharedImageItem],
    summary="List all active images shared with current user via permissions"
)
async def get_shared_with_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Fetch active images where the current user holds an active, non-expired permission."""
    now_utc = datetime.now(timezone.utc)
    stmt = (
        select(ImagePermission, RegisteredImage, PublicInformation, User)
        .join(RegisteredImage, ImagePermission.image_id == RegisteredImage.id)
        .outerjoin(PublicInformation, RegisteredImage.id == PublicInformation.image_id)
        .join(User, RegisteredImage.owner_id == User.id)
        .where(
            ImagePermission.user_id == current_user.id,
            RegisteredImage.status == ImageStatus.ACTIVE,
            (ImagePermission.expires_at == None) | (ImagePermission.expires_at > now_utc),
        )
        .order_by(ImagePermission.created_at.desc())
    )
    result = await db.execute(stmt)
    items = []
    for perm, img, pinfo, owner in result:
        items.append(
            SharedImageItem(
                id=img.id,
                public_image_uid=img.public_image_uid,
                title=pinfo.title if pinfo else "Untitled Image",
                description=pinfo.description if pinfo else None,
                access_level=perm.access_level.value,
                granted_by_email=owner.email if owner else None,
                owner_name=owner.full_name or owner.email,
                expires_at=perm.expires_at,
                status=img.status.value,
                created_at=perm.created_at,
            )
        )
    return items



@router.get(
    "/{public_image_uid}/download",
    summary="Download the registered image file",
    response_class=FileResponse,
)
async def download_image(
    public_image_uid: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Safely serve the registered image as a downloadable attachment.
    Enforces that:
    1. The image exists (404 if missing).
    2. The image is ACTIVE (403 if suspended).
    3. The file path on disk exists and resides securely within UPLOAD_DIR.
    """
    stmt = select(RegisteredImage).where(RegisteredImage.public_image_uid == public_image_uid)
    result = await db.execute(stmt)
    image = result.scalar_one_or_none()

    if not image:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image not found."
        )

    if image.status != ImageStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Image has been suspended and is unavailable for download."
        )

    target_path = Path(image.file_path).resolve()
    upload_root = settings.UPLOAD_DIR.resolve()

    # Prevent directory traversal
    try:
        target_path.relative_to(upload_root)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to requested file path is restricted."
        )

    if not target_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image file not found on server storage."
        )

    ext = target_path.suffix.lower().lstrip(".")
    media_type = "image/png"
    if ext in ("jpg", "jpeg"):
        media_type = "image/jpeg"
    elif ext == "webp":
        media_type = "image/webp"

    download_filename = f"IMAGEKEY_{image.public_image_uid}.{ext}" if ext else f"IMAGEKEY_{image.public_image_uid}.png"

    return FileResponse(
        path=str(target_path),
        filename=download_filename,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{download_filename}"'
        }
    )


@router.delete(
    "/{public_image_uid}",
    status_code=status.HTTP_200_OK,
    summary="Permanently delete registered image and associated storage files"
)
async def delete_image(
    public_image_uid: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Permanently delete the registered image record, cascading relations, and storage files.
    Restricted to image owner or platform administrator.
    """
    stmt = (
        select(RegisteredImage)
        .options(joinedload(RegisteredImage.public_info))
        .where(RegisteredImage.public_image_uid == public_image_uid)
    )
    result = await db.execute(stmt)
    image = result.unique().scalar_one_or_none()

    if not image:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Image with UID '{public_image_uid}' not found."
        )

    if image.owner_id != current_user.id and current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Only the image owner or an administrator can delete this registered image."
        )

    # 1. Clean up physical image file from storage
    if image.file_path:
        img_path = Path(image.file_path)
        if img_path.is_file():
            try:
                img_path.unlink()
            except Exception as e:
                logger.warning(f"Failed to delete image file {img_path}: {e}")

    # 2. Clean up attached PDF if present
    if image.public_info and image.public_info.services_json:
        for item in image.public_info.services_json:
            if isinstance(item, dict) and item.get("pdf_filename"):
                pdf_path = settings.UPLOAD_DIR / "pdfs" / item["pdf_filename"]
                if pdf_path.is_file():
                    try:
                        pdf_path.unlink()
                    except Exception as e:
                        logger.warning(f"Failed to delete attached PDF {pdf_path}: {e}")

    # 3. Delete database record (cascades public_info, private_info, permissions, access_logs)
    await db.delete(image)
    await db.commit()

    return {
        "status": "success",
        "message": f"Image '{public_image_uid}' and all linked assets have been permanently deleted."
    }


