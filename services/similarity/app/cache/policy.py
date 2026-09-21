from datetime import UTC, datetime

from app.cache.ttl import threshold_for_prompt
from app.store.vector import increment_hit_count


def isHit(score: float, expires_at: float, query_prompt: str) -> bool:
    threshold = threshold_for_prompt(query_prompt)
    if score < threshold:
        return False
    if expires_at < datetime.now(UTC).timestamp():
        return False
    return True


async def record_hit(result: dict, query_prompt: str) -> bool:
    """If this search result is a hit, increment Redis hit_count and return True."""
    if not isHit(result["score"], result["expires_at"], query_prompt):
        return False
    result["hit_count"] = await increment_hit_count(result["id"])
    return True
