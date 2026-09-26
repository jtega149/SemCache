from fastapi.testclient import TestClient

from app.main import app
from app.metrics import lookups, stores

LOOKUP_BODY = {
    "system_prompt": "You are helpful",
    "user_prompt": "What is the capital of France?",
    "model": "gpt-4o-mini",
    "temperature": 0,
    "max_tokens": 50,
}

PAYLOAD = {
    "text": "Paris",
    "prompt_tokens": 10,
    "completion_tokens": 2,
    "model_id": "gpt-4o-mini",
    "finish_reason": "stop",
}


def _sample(counter, result: str) -> float:
    for metric in counter.collect():
        for sample in metric.samples:
            if sample.name.endswith("_total") and sample.labels.get("result") == result:
                return sample.value
    return 0.0


def test_metrics_endpoint_lists_lookup_counter():
    response = TestClient(app).get("/metrics")
    assert response.status_code == 200
    assert "semcache_lookups_total" in response.text


def test_lookup_counts_each_outcome(monkeypatch):
    async def fake_embed(_prompt):
        return [0.0]

    async def fake_search(_vector, _namespace):
        return search_result

    async def fake_record_hit(_result, _prompt):
        return is_hit

    search_result = None
    is_hit = False
    monkeypatch.setattr("app.main.embed", fake_embed)
    monkeypatch.setattr("app.main.search", fake_search)
    monkeypatch.setattr("app.main.record_hit", fake_record_hit)
    client = TestClient(app)

    before_empty = _sample(lookups, "empty")
    response = client.post("/lookup", json=LOOKUP_BODY)
    assert response.status_code == 200
    assert response.json()["cached"] is False
    assert _sample(lookups, "empty") == before_empty + 1

    search_result = {"score": 0.99, "payload": PAYLOAD, "expires_at": 0, "id": "1"}
    is_hit = True
    before_hit = _sample(lookups, "hit")
    response = client.post("/lookup", json=LOOKUP_BODY)
    assert response.json()["cached"] is True
    assert _sample(lookups, "hit") == before_hit + 1

    is_hit = False
    before_near = _sample(lookups, "not_a_hit")
    response = client.post("/lookup", json=LOOKUP_BODY)
    assert response.json()["cached"] is False
    assert response.json()["similarity_score"] is None
    assert _sample(lookups, "not_a_hit") == before_near + 1


def test_store_counts_ttl_skip_and_successful_write(monkeypatch):
    async def fake_embed(_prompt):
        return [0.0]

    async def fake_upsert(_vector, _namespace, _prompt, _payload):
        return "point-1"

    monkeypatch.setattr("app.main.embed", fake_embed)
    monkeypatch.setattr("app.main.upsert", fake_upsert)
    client = TestClient(app)

    skip_body = {**LOOKUP_BODY, "user_prompt": "What is the weather right now?", "llm_payload": PAYLOAD}
    before_skip = _sample(stores, "ttl_skip")
    response = client.post("/store", json=skip_body)
    assert response.status_code == 200
    assert response.json()["id"] is None
    assert _sample(stores, "ttl_skip") == before_skip + 1

    store_body = {**LOOKUP_BODY, "llm_payload": PAYLOAD}
    before_stored = _sample(stores, "stored")
    response = client.post("/store", json=store_body)
    assert response.json()["id"] == "point-1"
    assert _sample(stores, "stored") == before_stored + 1
