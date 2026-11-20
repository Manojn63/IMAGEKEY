"""User ORM Model."""

import enum
from sqlalchemy import String, Boolean, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base
from app.models.base import UUIDPrimaryKeyMixin, TimestampMixin


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    OWNER = "owner"
    VIEWER = "viewer"


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role_enum", values_callable=lambda x: [e.value for e in x]),
        default=UserRole.VIEWER,
        nullable=False,
        index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    companies = relationship("Company", back_populates="owner", cascade="all, delete-orphan")
    registered_images = relationship("RegisteredImage", back_populates="owner", cascade="all, delete-orphan")
    permissions_received = relationship("ImagePermission", foreign_keys="ImagePermission.user_id", back_populates="user")
    permissions_granted = relationship("ImagePermission", foreign_keys="ImagePermission.granted_by", back_populates="granter")
    access_logs = relationship("AccessLog", back_populates="user")
