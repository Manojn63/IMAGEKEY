"""Rate Limiter Setup using Slowapi."""

import os
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.core.config import settings


def is_rate_limiting_enabled() -> bool:
    """Returns False during automated testing or when explicitly disabled."""
    if os.environ.get("TESTING") == "1" or settings.TESTING:
        return False
    return settings.RATE_LIMIT_ENABLED


limiter = Limiter(
    key_func=get_remote_address,
    enabled=is_rate_limiting_enabled(),
    default_limits=[f"{settings.RATE_LIMIT_PER_MINUTE}/minute"]
)
