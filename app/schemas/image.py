"""Image Registration and Metadata Schemas."""

import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class ImageRegisterResponse(BaseModel):
    id: uuid.UUID
    public_image_uid: str
    owner_id: uuid.UUID
    company_id: Optional[uuid.UUID] = None
    phash: str
    dhash: Optional[str] = None
    has_orb_descriptors: bool
    status: str
    title: str
    description: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MyImageItem(BaseModel):
    id: uuid.UUID
    public_image_uid: str
    title: str
    description: Optional[str] = None
    phash: str
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SharedImageItem(BaseModel):
    id: uuid.UUID
    public_image_uid: str
    title: str
    description: Optional[str] = None
    access_level: str
    granted_by_email: Optional[str] = None
    owner_name: Optional[str] = None
    expires_at: Optional[datetime] = None
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
