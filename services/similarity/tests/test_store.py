from app.store.vector import upsert, search
from app.models.schemas import LlmPayload

async def test_upsert_and_search():
    vector = [0.1] * 384
    namespace = "testing-123"
    user_prompt = "What is the capital of France?"
    payload = LlmPayload(
        text="Paris",
        prompt_tokens=10,
        completion_tokens=10,
        model_id="gpt-4o",
        finish_reason="stop"
    )

    point_id = await upsert(vector, namespace, user_prompt, payload)
    assert point_id is not None

    result = await search(vector, namespace)
    assert result is not None
    assert result["id"] == f"semcache:{point_id}"
    assert result["user_prompt"] == user_prompt
    assert result["payload"] == payload
    assert result["score"] is not None
    assert result["score"] > 0.0
    assert result["score"] >= 0.95
    assert result["score"] is not None