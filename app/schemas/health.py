"""Health check schemas."""

from typing import Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field


class DatabaseHealth(BaseModel):
    status: str
    healthy: bool
    error: Optional[str] = None
    hint: Optional[str] = None


class HealthResponse(BaseModel):
    app: str = "IMAGEKEY"
    status: str = "ok"
    version: str = "1.0.0"
    environment: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    database: DatabaseHealth
    features: Dict[str, Any]
