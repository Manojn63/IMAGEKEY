"""Image Recognition and Optical Scanning API Routes."""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status, Request
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.limiter import limiter
from app.models.image import RegisteredImage, ImageStatus
from app.models.access_log import AccessLog, AuditActionType
from app.schemas.scanner import ScanResponse, ScanMatchDetail
from app.services.vision import (
    sanitize_and_strip_exif,
    match_query_against_candidates,
    MatchVerdict,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/identify",
    response_model=ScanResponse,
    status_code=status.HTTP_200_OK,
    summary="Scan and identify an image query against registered optical keys"
)
@limiter.limit("30/minute")
async def identify_image(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Public Image Identification & Recognition Pipeline:
    1. Validate upload size (<= 5MB) and supported MIME types.
    2. Strip EXIF and sanitize memory representation.
    3. Query all active registered images from the vault.
    4. Two-Tier Matching: Stage 1 (pHash/dHash Hamming distance) + Stage 2 (OpenCV ORB BFMatcher).
    5. Evaluate confidence score against strict thresholds (>=85% VERIFIED, 65-84% UNCERTAIN, <65% NO_MATCH).
    6. Record immutable audit entry in access_logs (scan_success / scan_fail).
    7. Return ScanResponse with verified public metadata.
    
    ZERO-TRUST ENFORCEMENT:
    Under no circumstances is private_information queried or exposed through this endpoint.
    """
    # 1. Validate file size
    raw_bytes = await file.read()
    if len(raw_bytes) > settings.MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"Image exceeds maximum permitted size of {settings.MAX_FILE_SIZE_BYTES // (1024*1024)}MB."
        )

    if len(raw_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded scan file is empty."
        )

    # 2. Sanitize and strip EXIF
    try:
        clean_pil, _ = sanitize_and_strip_exif(raw_bytes)
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve)
        )

    # 3. Fetch active registered candidate images with public relations
    stmt = (
        select(RegisteredImage)
        .options(
            joinedload(RegisteredImage.public_info),
            joinedload(RegisteredImage.company),
        )
        .where(RegisteredImage.status == ImageStatus.ACTIVE)
    )
    result = await db.execute(stmt)
    candidates = result.unique().scalars().all()

    # 4. Two-Tier Computer Vision Matching
    verdict, confidence_score, best_candidate, diagnostics = match_query_against_candidates(
        query_pil=clean_pil,
        candidates=candidates,
    )
    confidence_score = float(confidence_score)
    confidence_pct = float(round(confidence_score * 100.0, 1))

    # 5. Audit Logging
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")[:500]

    action = (
        AuditActionType.SCAN_SUCCESS
        if verdict == MatchVerdict.VERIFIED_MATCH
        else AuditActionType.SCAN_FAIL
    )

    audit_entry = AccessLog(
        image_id=best_candidate.id if (best_candidate and verdict == MatchVerdict.VERIFIED_MATCH) else None,
        user_id=None,  # Public scanning, unauthenticated
        action_type=action,
        ip_address=client_ip,
        user_agent=user_agent,
        confidence_score=confidence_score,
    )
    db.add(audit_entry)
    await db.commit()

    # 6. Response Construction with Zero-Trust Public Payload
    match_detail: Optional[ScanMatchDetail] = None

    if verdict == MatchVerdict.VERIFIED_MATCH and best_candidate:
        pinfo = best_candidate.public_info
        comp = best_candidate.company
        auto_redirect = False
        has_pdf = False
        pdf_url = None
        if pinfo and pinfo.services_json:
            for item in pinfo.services_json:
                if isinstance(item, dict) and item.get("__meta__"):
                    auto_redirect = bool(item.get("auto_redirect", False))
                    if item.get("pdf_filename"):
                        has_pdf = True
                        pdf_url = f"/api/v1/public-info/{best_candidate.public_image_uid}/pdf"
                    break

        match_detail = ScanMatchDetail(
            public_image_uid=best_candidate.public_image_uid,
            title=pinfo.title if pinfo else "Registered Optical Key",
            description=pinfo.description if pinfo else None,
            company_name=comp.name if comp else None,
            website_url=pinfo.website_url if (pinfo and pinfo.website_url) else (comp.website if comp else None),
            contact_email=pinfo.contact_email if pinfo else None,
            contact_phone=pinfo.contact_phone if pinfo else None,
            auto_redirect=auto_redirect,
            has_pdf=has_pdf,
            pdf_url=pdf_url,
        )
        message = "Image verified successfully in Optical Vault."
    elif verdict == MatchVerdict.UNCERTAIN:
        message = "Optical match uncertain. Hold camera steady, improve lighting, or avoid glare."
    else:
        message = "No matching registered image found in Optical Vault."

    return ScanResponse(
        verdict=verdict,
        confidence_score=confidence_score,
        confidence_percentage=confidence_pct,
        message=message,
        match=match_detail,
        diagnostic_info=diagnostics if settings.DEBUG else None,
    )
