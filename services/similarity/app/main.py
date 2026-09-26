import time

from fastapi import FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.models.schemas import LookupRequest, LookupResponse, StoreRequest, StoreResponse
from app.embeddings.openai import embed
from app.store.vector import upsert, search
from app.cache.key import build_namespace
from app.cache.policy import record_hit
from app.cache.ttl import ttl_for_prompt
from app.api.routes.delete_route import router as delete_router
from app.metrics import lookup_seconds, lookups, stores

app = FastAPI()
app.include_router(delete_router)

@app.get("/")
async def root():
    return {"message": "Hello, this is the similarity service"}

@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

@app.post("/lookup", response_model=LookupResponse)
async def lookup(request: LookupRequest):
    started = time.perf_counter()
    try:
        vector = await embed(request.user_prompt)
        namespace = build_namespace(request.system_prompt, request.model, request.temperature, request.max_tokens)
        result = await search(vector, namespace)
        if result is None:
            lookups.labels(result="empty").inc()
            return LookupResponse(cached=False, similarity_score=None, payload=None)
        if await record_hit(result, request.user_prompt):
            lookups.labels(result="hit").inc()
            return LookupResponse(cached=True, similarity_score=result["score"], payload=result["payload"])
        lookups.labels(result="not_a_hit").inc()
        return LookupResponse(cached=False, similarity_score=None, payload=None)
    finally:
        lookup_seconds.observe(time.perf_counter() - started)

@app.post("/store", response_model=StoreResponse)
async def store(request: StoreRequest):
    if ttl_for_prompt(request.user_prompt) == 0:
        stores.labels(result="ttl_skip").inc()
        return StoreResponse(id=None, success=True)
    vector = await embed(request.user_prompt)
    namespace = build_namespace(request.system_prompt, request.model, request.temperature, request.max_tokens)
    point_id = await upsert(vector, namespace, request.user_prompt, request.llm_payload)
    if point_id is None:
        return StoreResponse(id=None, success=True)
    stores.labels(result="stored").inc()
    return StoreResponse(id=point_id, success=True)