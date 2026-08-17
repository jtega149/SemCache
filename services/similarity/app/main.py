from fastapi import FastAPI
from app.models.schemas import LookupRequest, LookupResponse, StoreRequest, StoreResponse
from app.embeddings.openai import embed
from app.store.vector import upsert, search
from app.cache.key import build_namespace
from app.cache.policy import record_hit

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Hello, this is the similarity service"}

@app.post("/lookup", response_model=LookupResponse)
async def lookup(request: LookupRequest):
    vector = await embed(request.user_prompt)
    namespace = build_namespace(request.system_prompt, request.model, request.temperature, request.max_tokens)
    result = await search(vector, namespace)
    if result is None:
        return LookupResponse(cached=False, similarity_score=None, payload=None)
    if await record_hit(result):
        return LookupResponse(cached=True, similarity_score=result["score"], payload=result["payload"])
    return LookupResponse(cached=False, similarity_score=None, payload=None)

@app.post("/store", response_model=StoreResponse)
async def store(request: StoreRequest):
    vector = await embed(request.user_prompt)
    namespace = build_namespace(request.system_prompt, request.model, request.temperature, request.max_tokens)
    point_id = await upsert(vector, namespace, request.user_prompt, request.llm_payload)
    if point_id is None:
        return StoreResponse(id=None, success=False)
    return StoreResponse(id=point_id, success=True)