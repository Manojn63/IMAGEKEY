"""RegisteredImage ORM Model."""

import uuid
import enum
from sqlalchemy import String, ForeignKey, Enum, LargeBinary, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base
from app.models.base import UUIDPrimaryKeyMixin, TimestampMixin


class ImageStatus(str, enum.Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class RegisteredImage(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "registered_images"

    # Unique public reference ID (e.g. IMG-7K9A2X) - NOT an auth secret
    public_image_uid: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("companies.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    phash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    dhash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    orb_descriptors: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    status: Mapped[ImageStatus] = mapped_column(
        Enum(ImageStatus, name="image_status_enum", values_callable=lambda x: [e.value for e in x]),
        default=ImageStatus.ACTIVE,
        nullable=False,
        index=True
    )

    # Relationships
    owner = relationship("User", back_populates="registered_images")
    company = relationship("Company", back_populates="images")
    public_info = relationship("PublicInformation", back_populates="image", uselist=False, cascade="all, delete-orphan")
    private_info = relationship("PrivateInformation", back_populates="image", uselist=False, cascade="all, delete-orphan")
    permissions = relationship("ImagePermission", back_populates="image", cascade="all, delete-orphan")
    access_logs = relationship("AccessLog", back_populates="image", cascade="all, delete-orphan")
