"""Schemas for Public and Private Tiered Information Vault."""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator, ConfigDict


class PublicInfoUpdateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=5000)
    website_url: Optional[str] = Field(None, max_length=500)
    contact_email: Optional[str] = Field(None, max_length=255)
    contact_phone: Optional[str] = Field(None, max_length=50)
    services_json: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    auto_redirect: Optional[bool] = False

    @field_validator("website_url")
    @classmethod
    def validate_website_url(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v.strip() == "":
            return None
        v_clean = v.strip()
        if not (v_clean.startswith("http://") or v_clean.startswith("https://")):
            raise ValueError("Website URL must start with http:// or https://")
        return v_clean

    @field_validator("contact_email")
    @classmethod
    def validate_contact_email(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v.strip() == "":
            return None
        v_clean = v.strip()
        if "@" not in v_clean or "." not in v_clean.split("@")[-1]:
            raise ValueError("Invalid email format.")
        return v_clean


class PublicInfoResponse(BaseModel):
    public_image_uid: str
    title: str
    description: Optional[str] = None
    website_url: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    services_json: Optional[List[Dict[str, Any]]] = None
    company_name: Optional[str] = None
    company_website: Optional[str] = None
    has_private_vault: bool = False
    auto_redirect: bool = False
    has_pdf: bool = False
    pdf_url: Optional[str] = None
    pdf_original_name: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class PrivateInfoUpdateRequest(BaseModel):
    confidential_notes: Optional[str] = Field(None, max_length=10000)
    internal_data_json: Optional[Dict[str, Any]] = Field(default_factory=dict)
    document_paths_json: Optional[List[str]] = Field(default_factory=list)


class PrivateInfoResponse(BaseModel):
    public_image_uid: str
    title: str
    confidential_notes: Optional[str] = None
    internal_data_json: Optional[Dict[str, Any]] = None
    document_paths_json: Optional[List[str]] = None
    user_access_level: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
