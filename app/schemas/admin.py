"""Admin Management Schemas."""

import uuid
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict
from app.models.image import ImageStatus


class AdminOverviewResponse(BaseModel):
    total_users: int
    total_images: int
    active_images: int
    suspended_images: int
    total_scans: int
    unauthorized_attempts: int


class AdminUserItem(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: str
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AdminUserStatusUpdate(BaseModel):
    is_active: bool


class AdminImageItem(BaseModel):
    id: uuid.UUID
    public_image_uid: str
    title: str
    owner_email: str
    company_name: Optional[str] = None
    status: str
    phash: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AdminImageStatusUpdate(BaseModel):
    status: ImageStatus


class AdminLogItem(BaseModel):
    id: uuid.UUID
    image_uid: Optional[str] = None
    user_email: Optional[str] = None
    action_type: str
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    confidence_score: Optional[float] = None
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)


class AdminLogsResponse(BaseModel):
    total: int
    logs: List[AdminLogItem]
