from datetime import UTC, datetime

from app.config import settings
from app.store.vector import increment_hit_count


def isHit(score: float, expires_at: float) -> bool:
    threshold = float(settings.similarity_threshold)
    if score < threshold:
        return False
    if expires_at < datetime.now(UTC).timestamp():
        return False
    return True


async def record_hit(result: dict) -> bool:
    """If this search result is a hit, increment Redis hit_count and return True."""
    if not isHit(result["score"], result["expires_at"]):
        return False
    result["hit_count"] = await increment_hit_count(result["id"])
    return True
