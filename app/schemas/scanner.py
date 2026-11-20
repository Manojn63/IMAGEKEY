"""Scanner Schemas for Image Recognition and Match Responses."""

from typing import Optional, Dict, Any
from pydantic import BaseModel, ConfigDict


class ScanMatchDetail(BaseModel):
    public_image_uid: str
    title: Optional[str] = None
    description: Optional[str] = None
    company_name: Optional[str] = None
    website_url: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    auto_redirect: bool = False
    has_pdf: bool = False
    pdf_url: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ScanResponse(BaseModel):
    verdict: str  # VERIFIED_MATCH, UNCERTAIN, NO_MATCH
    confidence_score: float
    confidence_percentage: float
    message: str
    match: Optional[ScanMatchDetail] = None
    diagnostic_info: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)
