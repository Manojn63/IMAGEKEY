"""Image Access Permissions ORM Model."""

import uuid
import enum
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Enum, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base
from app.models.base import UUIDPrimaryKeyMixin, TimestampMixin


class AccessLevel(str, enum.Enum):
    VIEW_PRIVATE = "view_private"
    EDIT = "edit"


class ImagePermission(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "image_permissions"

    image_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("registered_images.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    access_level: Mapped[AccessLevel] = mapped_column(
        Enum(AccessLevel, name="access_level_enum", values_callable=lambda x: [e.value for e in x]),
        default=AccessLevel.VIEW_PRIVATE,
        nullable=False
    )
    granted_by: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    image = relationship("RegisteredImage", back_populates="permissions")
    user = relationship("User", foreign_keys=[user_id], back_populates="permissions_received")
    granter = relationship("User", foreign_keys=[granted_by], back_populates="permissions_granted")
