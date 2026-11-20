"""Public Information CRUD and Retrieval API Routes."""

import os
import uuid
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from fastapi import APIRouter, Depends, HTTPException, status, Request, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User, UserRole
from app.models.image import RegisteredImage, ImageStatus
from app.models.information import PublicInformation
from app.models.access_log import AccessLog, AuditActionType
from app.schemas.information import PublicInfoResponse, PublicInfoUpdateRequest

logger = logging.getLogger(__name__)

router = APIRouter()


def extract_meta_from_services(services_list: Optional[list]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Separates customer-facing service tags from internal optical metadata."""
    cleaned = []
    meta = {}
    if services_list:
        for item in services_list:
            if isinstance(item, dict) and item.get("__meta__"):
                meta = dict(item)
            elif isinstance(item, dict):
                cleaned.append(item)
            elif isinstance(item, str):
                cleaned.append({"name": item})
    return cleaned, meta


@router.get(
    "/{public_image_uid}",
    response_model=PublicInfoResponse,
    status_code=status.HTTP_200_OK,
    summary="Get public information for a registered image"
)
async def get_public_info(
    public_image_uid: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Open Public Display Endpoint:
    - Publicly accessible to all viewers without login.
    - Queries public information, company info, and private vault presence.
    - Strictly ZERO-TRUST: NEVER returns or queries private vault contents.
    - Automatically records a `view_public` access audit event.
    """
    stmt = (
        select(RegisteredImage)
        .options(
            joinedload(RegisteredImage.public_info),
            joinedload(RegisteredImage.company),
            joinedload(RegisteredImage.private_info),
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

    # Record public view audit log
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")[:500]

    audit_entry = AccessLog(
        image_id=image.id,
        user_id=None,
        action_type=AuditActionType.VIEW_PUBLIC,
        ip_address=client_ip,
        user_agent=user_agent,
        confidence_score=1.0,
    )
    db.add(audit_entry)
    await db.commit()

    pinfo = image.public_info
    comp = image.company
    has_private = image.private_info is not None

    cleaned_services, meta = extract_meta_from_services(pinfo.services_json if pinfo else [])
    auto_redirect = bool(meta.get("auto_redirect", False))
    pdf_filename = meta.get("pdf_filename")
    pdf_original_name = meta.get("pdf_original_name")
    has_pdf = bool(pdf_filename)
    pdf_url = f"/api/v1/public-info/{image.public_image_uid}/pdf" if has_pdf else None

    return PublicInfoResponse(
        public_image_uid=image.public_image_uid,
        title=pinfo.title if pinfo else "Registered Optical Key",
        description=pinfo.description if pinfo else None,
        website_url=pinfo.website_url if pinfo else None,
        contact_email=pinfo.contact_email if pinfo else None,
        contact_phone=pinfo.contact_phone if pinfo else None,
        services_json=cleaned_services,
        company_name=comp.name if comp else None,
        company_website=comp.website if comp else None,
        has_private_vault=has_private,
        auto_redirect=auto_redirect,
        has_pdf=has_pdf,
        pdf_url=pdf_url,
        pdf_original_name=pdf_original_name,
        created_at=pinfo.created_at if pinfo else image.created_at,
        updated_at=pinfo.updated_at if pinfo else image.updated_at,
    )


@router.put(
    "/{public_image_uid}",
    response_model=PublicInfoResponse,
    status_code=status.HTTP_200_OK,
    summary="Update public information for a registered image (Owner or Admin only)"
)
async def update_public_info(
    public_image_uid: str,
    payload: PublicInfoUpdateRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Protected Public Info Editor Endpoint:
    - Requires authentication.
    - Enforces ownership: only the image owner or an admin may modify details.
    - Validates inputs strictly (e.g. website_url must be http:// or https://).
    - Stores auto_redirect cleanly in metadata.
    - Logs modification in access audit log.
    """
    stmt = (
        select(RegisteredImage)
        .options(
            joinedload(RegisteredImage.public_info),
            joinedload(RegisteredImage.company),
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

    # Ownership check
    if image.owner_id != current_user.id and current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You do not have permission to modify this registered image."
        )

    pinfo = image.public_info

    # Extract existing metadata and update auto_redirect
    _, current_meta = extract_meta_from_services(pinfo.services_json if pinfo else [])
    if payload.auto_redirect is not None:
        current_meta["auto_redirect"] = bool(payload.auto_redirect)
    current_meta["__meta__"] = True

    # Assemble cleaned services + metadata dictionary
    new_services = [s for s in (payload.services_json or []) if not (isinstance(s, dict) and s.get("__meta__"))]
    new_services.append(current_meta)

    if not pinfo:
        pinfo = PublicInformation(
            image_id=image.id,
            title=payload.title.strip(),
            description=payload.description.strip() if payload.description else None,
            website_url=payload.website_url,
            contact_email=payload.contact_email,
            contact_phone=payload.contact_phone,
            services_json=new_services,
        )
        db.add(pinfo)
    else:
        pinfo.title = payload.title.strip()
        pinfo.description = payload.description.strip() if payload.description else None
        pinfo.website_url = payload.website_url
        pinfo.contact_email = payload.contact_email
        pinfo.contact_phone = payload.contact_phone
        pinfo.services_json = new_services
        flag_modified(pinfo, "services_json")

    # Audit log entry for update
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
    await db.refresh(pinfo)

    comp = image.company
    has_private = image.private_info is not None

    cleaned_services, meta = extract_meta_from_services(pinfo.services_json)
    auto_redirect = bool(meta.get("auto_redirect", False))
    pdf_filename = meta.get("pdf_filename")
    pdf_original_name = meta.get("pdf_original_name")
    has_pdf = bool(pdf_filename)
    pdf_url = f"/api/v1/public-info/{image.public_image_uid}/pdf" if has_pdf else None

    return PublicInfoResponse(
        public_image_uid=image.public_image_uid,
        title=pinfo.title,
        description=pinfo.description,
        website_url=pinfo.website_url,
        contact_email=pinfo.contact_email,
        contact_phone=pinfo.contact_phone,
        services_json=cleaned_services,
        company_name=comp.name if comp else None,
        company_website=comp.website if comp else None,
        has_private_vault=has_private,
        auto_redirect=auto_redirect,
        has_pdf=has_pdf,
        pdf_url=pdf_url,
        pdf_original_name=pdf_original_name,
        created_at=pinfo.created_at,
        updated_at=pinfo.updated_at,
    )


@router.post(
    "/{public_image_uid}/pdf",
    status_code=status.HTTP_201_CREATED,
    summary="Upload PDF attachment for a registered image (Owner or Admin only)"
)
async def upload_pdf_document(
    public_image_uid: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload and securely attach a PDF document (max 10MB) to public information.
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
            detail="Access denied. Only the image owner or an administrator can attach documents."
        )

    raw_bytes = await file.read()
    if len(raw_bytes) > 10 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="PDF exceeds maximum allowed size of 10MB."
        )

    if len(raw_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded PDF file is empty."
        )

    filename_lower = (file.filename or "").lower()
    if not filename_lower.endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file extension. Only .pdf documents are allowed."
        )

    if not raw_bytes.startswith(b"%PDF"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file format. File does not have a valid PDF magic header (%PDF)."
        )

    pdf_dir = settings.UPLOAD_DIR / "pdfs"
    pdf_dir.mkdir(parents=True, exist_ok=True)

    storage_filename = f"{uuid.uuid4().hex}.pdf"
    storage_path = pdf_dir / storage_filename

    with open(storage_path, "wb") as f:
        f.write(raw_bytes)

    pinfo = image.public_info
    if not pinfo:
        pinfo = PublicInformation(
            image_id=image.id,
            title="Registered Optical Key",
            services_json=[],
        )
        db.add(pinfo)
        await db.flush()

    cleaned_services, meta = extract_meta_from_services(pinfo.services_json or [])
    # Clean up previous PDF file if exists
    old_pdf = meta.get("pdf_filename")
    if old_pdf:
        old_path = pdf_dir / old_pdf
        if old_path.is_file():
            try:
                old_path.unlink()
            except Exception as e:
                logger.warning(f"Failed to delete old PDF {old_path}: {e}")

    meta["__meta__"] = True
    meta["pdf_filename"] = storage_filename
    meta["pdf_original_name"] = file.filename or "document.pdf"

    new_services = cleaned_services + [meta]
    pinfo.services_json = new_services
    flag_modified(pinfo, "services_json")

    await db.commit()
    await db.refresh(pinfo)

    return {
        "status": "success",
        "message": "PDF uploaded and attached successfully.",
        "has_pdf": True,
        "pdf_filename": storage_filename,
        "pdf_original_name": meta["pdf_original_name"],
        "pdf_url": f"/api/v1/public-info/{public_image_uid}/pdf"
    }


@router.get(
    "/{public_image_uid}/pdf",
    summary="View or download attached public PDF document inline",
    response_class=FileResponse
)
async def get_pdf_document(
    public_image_uid: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Serve attached public PDF document with inline Content-Disposition for browser viewing.
    """
    stmt = (
        select(RegisteredImage)
        .options(joinedload(RegisteredImage.public_info))
        .where(
            RegisteredImage.public_image_uid == public_image_uid,
            RegisteredImage.status == ImageStatus.ACTIVE,
        )
    )
    result = await db.execute(stmt)
    image = result.unique().scalar_one_or_none()

    if not image or not image.public_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image not found or inactive."
        )

    _, meta = extract_meta_from_services(image.public_info.services_json or [])
    pdf_filename = meta.get("pdf_filename")
    pdf_original_name = meta.get("pdf_original_name") or "document.pdf"

    if not pdf_filename:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No PDF document is attached to this optical key."
        )

    pdf_dir = (settings.UPLOAD_DIR / "pdfs").resolve()
    target_path = (pdf_dir / pdf_filename).resolve()

    try:
        target_path.relative_to(pdf_dir)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to requested file is forbidden."
        )

    if not target_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attached PDF file not found on server storage."
        )

    return FileResponse(
        path=str(target_path),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{pdf_original_name}"'
        }
    )

