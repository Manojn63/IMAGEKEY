"""Audit Access Logs ORM Model."""

import uuid
import enum
from datetime import datetime, timezone
from sqlalchemy import String, Float, DateTime, ForeignKey, Enum, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base
from app.models.base import UUIDPrimaryKeyMixin


class AuditActionType(str, enum.Enum):
    SCAN_SUCCESS = "scan_success"
    SCAN_FAIL = "scan_fail"
    VIEW_PUBLIC = "view_public"
    VIEW_PRIVATE = "view_private"
    UNAUTHORIZED_ATTEMPT = "unauthorized_attempt"
    PERMISSION_CHANGE = "permission_change"


class AccessLog(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "access_logs"

    image_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("registered_images.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    action_type: Mapped[AuditActionType] = mapped_column(
        Enum(AuditActionType, name="audit_action_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        index=True
    )
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True
    )

    # Relationships
    image = relationship("RegisteredImage", back_populates="access_logs")
    user = relationship("User", back_populates="access_logs")
