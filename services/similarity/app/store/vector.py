from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import uuid4

from redisvl.index import AsyncSearchIndex
from redisvl.query import VectorQuery
from redisvl.query.filter import Tag

from app.config import settings
from app.models.schemas import LlmPayload

INDEX_SCHEMA = {
    "index": {
        "name": "semcache",
        "prefix": "semcache",
        "storage_type": "json",
    },
    "fields": [
        {"name": "namespace", "type": "tag"},
        {"name": "user_prompt", "type": "text"},
        {"name": "text", "type": "text"},
        {"name": "prompt_tokens", "type": "numeric"},
        {"name": "completion_tokens", "type": "numeric"},
        {"name": "model_id", "type": "tag"},
        {"name": "finish_reason", "type": "tag"},
        {"name": "created_at", "type": "numeric"},
        {"name": "expires_at", "type": "numeric"},
        {"name": "hit_count", "type": "numeric"},
        {
            "name": "embedding",
            "type": "vector",
            "attrs": {
                "dims": 384,
                "distance_metric": "cosine",
                "algorithm": "flat",
                "datatype": "float32",
            },
        },
    ],
}

_index: AsyncSearchIndex | None = None


def _namespace_tag(namespace: str) -> str:
    # TAG fields split on punctuation (-, :, =). Hash keeps an exact-match filter.
    return sha256(namespace.encode()).hexdigest()


async def get_index() -> AsyncSearchIndex:
    global _index
    if _index is None:
        _index = AsyncSearchIndex.from_dict(
            INDEX_SCHEMA,
            redis_url=settings.redis_url,
        )
        if not await _index.exists():
            await _index.create()
    return _index


async def upsert(
    vector: list[float],
    namespace: str,
    user_prompt: str,
    payload: LlmPayload,
) -> str:
    """After a cache miss + LLM response, write the vector into Redis."""
    index = await get_index()

    point_id = str(uuid4())
    created_at = datetime.now(UTC)
    ttl_seconds = settings.default_ttl_seconds
    expires_at = created_at + timedelta(seconds=ttl_seconds)

    document = {
        "id": point_id,
        "namespace": _namespace_tag(namespace),
        "user_prompt": user_prompt,
        "text": payload.text,
        "prompt_tokens": payload.prompt_tokens,
        "completion_tokens": payload.completion_tokens,
        "model_id": payload.model_id,
        "finish_reason": payload.finish_reason,
        "created_at": created_at.timestamp(),
        "expires_at": expires_at.timestamp(),
        "hit_count": 0,
        "embedding": vector,
    }

    await index.load([document], id_field="id", ttl=ttl_seconds)
    return point_id


def redis_key(point_id: str) -> str:
    prefix = INDEX_SCHEMA["index"]["prefix"]
    if point_id.startswith(f"{prefix}:"):
        return point_id
    return f"{prefix}:{point_id}"


async def increment_hit_count(point_id: str) -> int:
    index = await get_index()
    client = await index._get_client()
    updated = await client.json().numincrby(redis_key(point_id), "$.hit_count", 1)
    if isinstance(updated, list):
        updated = updated[0]
    return int(updated)


async def search(vector: list[float], namespace: str) -> dict | None:
    index = await get_index()

    query = VectorQuery(
        vector=vector,
        vector_field_name="embedding",
        num_results=1,
        return_fields=[
            "user_prompt",
            "text",
            "prompt_tokens",
            "completion_tokens",
            "model_id",
            "finish_reason",
            "created_at",
            "expires_at",
            "hit_count",
        ],
        filter_expression=Tag("namespace") == _namespace_tag(namespace),
    )

    results = await index.query(query)
    if not results:
        return None

    hit = results[0]
    distance = float(hit["vector_distance"])

    return {
        "id": hit["id"],
        "score": 1.0 - distance,
        "user_prompt": hit["user_prompt"],
        "payload": LlmPayload(
            text=hit["text"],
            prompt_tokens=int(hit["prompt_tokens"]),
            completion_tokens=int(hit["completion_tokens"]),
            model_id=hit["model_id"],
            finish_reason=hit["finish_reason"],
        ),
        "created_at": float(hit["created_at"]),
        "expires_at": float(hit["expires_at"]),
        "hit_count": int(hit["hit_count"]),
    }
