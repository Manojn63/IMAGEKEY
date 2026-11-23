"""System and Data Sync Status Service.

Tracks changes across registered images, public information, and permissions
to produce a fast, deterministic version signature and timestamp for client auto-sync.
"""

import hashlib
import time
import logging
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.image import RegisteredImage
from app.models.information import PublicInformation
from app.models.permission import ImagePermission

logger = logging.getLogger(__name__)

_STARTUP_EPOCH = int(time.time())


async def compute_sync_status(db: AsyncSession) -> dict:
    """
    Computes a lightweight deterministic hash signature representing current database state.
    Returns:
        dict: { "version": "<sha256_slice>", "timestamp": <unix_epoch>, "status": "ok" }
    """
    try:
        # 1. Total images count & latest updated timestamp
        img_stmt = select(
            func.count(RegisteredImage.id),
            func.max(RegisteredImage.updated_at),
            func.max(RegisteredImage.created_at)
        )
        img_res = await db.execute(img_stmt)
        img_count, img_max_updated, img_max_created = img_res.first() or (0, None, None)

        # 2. Public information latest updated timestamp
        pub_stmt = select(func.max(PublicInformation.updated_at))
        pub_res = await db.execute(pub_stmt)
        pub_max_updated = pub_res.scalar()

        # 3. Permissions count
        perm_stmt = select(func.count(ImagePermission.id))
        perm_res = await db.execute(perm_stmt)
        perm_count = perm_res.scalar() or 0

        # Construct raw digest key
        img_up_str = img_max_updated.isoformat() if img_max_updated else "none"
        img_cr_str = img_max_created.isoformat() if img_max_created else "none"
        pub_up_str = pub_max_updated.isoformat() if pub_max_updated else "none"

        raw_digest = f"{img_count}_{img_up_str}_{img_cr_str}_{pub_up_str}_{perm_count}"
        version_hash = hashlib.sha256(raw_digest.encode("utf-8")).hexdigest()[:16]

        # Determine latest epoch
        candidates = [dt for dt in (img_max_updated, img_max_created, pub_max_updated) if dt is not None]
        if candidates:
            latest_dt = max(candidates)
            epoch = int(latest_dt.timestamp())
        else:
            epoch = _STARTUP_EPOCH

        return {
            "version": version_hash,
            "timestamp": epoch,
            "status": "ok"
        }
    except Exception as exc:
        logger.warning("Error computing sync status from DB: %s. Using boot fallback.", exc)
        return {
            "version": f"boot_{_STARTUP_EPOCH}",
            "timestamp": int(time.time()),
            "status": "ok"
        }
