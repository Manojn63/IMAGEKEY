"""Database Connection and Session Management."""

import logging
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
from app.core.config import settings

logger = logging.getLogger(__name__)

# Normalize sqlite URL for aiosqlite if sqlite is provided
db_url = settings.DATABASE_URL
if db_url.startswith("sqlite://"):
    db_url = db_url.replace("sqlite://", "sqlite+aiosqlite://", 1)

# Configure engine arguments dynamically based on database dialect
engine_kwargs = {
    "echo": settings.DB_ECHO,
    "future": True,
    "pool_pre_ping": True,
}

if "sqlite" in db_url:
    # SQLite requires check_same_thread=False for async thread pooling and rejects PostgreSQL pool params
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    # PostgreSQL connection pool arguments
    engine_kwargs["pool_size"] = 10
    engine_kwargs["max_overflow"] = 20

# Initialize asynchronous engine
engine = create_async_engine(
    db_url,
    **engine_kwargs,
)

# Async session factory
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """Base declarative class for all SQLAlchemy ORM models."""
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency that provides an async SQLAlchemy session per request."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """Create database tables if they do not exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def check_db_connection() -> dict:
    """Utility to test database connectivity for health checks."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "connected", "healthy": True}
    except Exception as exc:
        logger.warning("Database connectivity check failed: %s", exc)
        hint = (
            "Ensure SQLite file permissions and directory path are writable."
            if "sqlite" in db_url
            else "Ensure PostgreSQL is running via 'docker compose up -d' or local service."
        )
        return {
            "status": "disconnected",
            "healthy": False,
            "error": str(exc),
            "hint": hint,
        }
