"""Sync Status API Schemas."""

from pydantic import BaseModel, Field


class SyncStatusResponse(BaseModel):
    version: str = Field(..., description="Unique hash or version token reflecting latest database state")
    timestamp: int = Field(..., description="Unix epoch timestamp in seconds")
    status: str = Field(default="ok", description="System operational status indicator")
