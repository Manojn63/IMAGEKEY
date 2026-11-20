"""Public and Private Information ORM Models (Tiered Vault)."""

import uuid
from typing import Any, Dict, List
from sqlalchemy import String, Text, ForeignKey, JSON, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base
from app.models.base import UUIDPrimaryKeyMixin, TimestampMixin


class PublicInformation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Openly accessible metadata linked to a registered image."""
    __tablename__ = "public_information"

    image_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("registered_images.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    website_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    services_json: Mapped[List[Dict[str, Any]] | None] = mapped_column(JSON, default=list, nullable=True)

    # Relationship
    image = relationship("RegisteredImage", back_populates="public_info")


class PrivateInformation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Confidential metadata strictly guarded by RBAC permissions."""
    __tablename__ = "private_information"

    image_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("registered_images.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True
    )
    confidential_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    internal_data_json: Mapped[Dict[str, Any] | None] = mapped_column(JSON, default=dict, nullable=True)
    document_paths_json: Mapped[List[str] | None] = mapped_column(JSON, default=list, nullable=True)

    # Relationship
    image = relationship("RegisteredImage", back_populates="private_info")
