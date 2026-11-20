"""Access Permission Schemas for Granular Vault Sharing."""

import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from app.models.permission import AccessLevel


class PermissionGrantRequest(BaseModel):
    email: EmailStr
    access_level: AccessLevel = AccessLevel.VIEW_PRIVATE
    expires_at: Optional[datetime] = None


class PermissionItemResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    user_email: str
    user_full_name: str
    access_level: str
    granted_by: uuid.UUID
    expires_at: Optional[datetime] = None
    is_expired: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
