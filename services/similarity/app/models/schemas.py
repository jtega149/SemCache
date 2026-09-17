# request/response Pydantic models
from pydantic import BaseModel

class CacheableRequest(BaseModel):
    system_prompt: str
    user_prompt: str
    model: str
    temperature: float
    max_tokens: int

class LlmPayload(BaseModel):
    text: str
    prompt_tokens: int
    completion_tokens: int
    model_id: str
    finish_reason: str

class LookupRequest(CacheableRequest):
    pass

class LookupResponse(BaseModel):
    cached: bool
    similarity_score: float | None = None
    payload: LlmPayload | None = None

class StoreRequest(CacheableRequest):
    llm_payload: LlmPayload

class StoreResponse(BaseModel):
    id: str | None = None
    success: bool

class DeleteNamespaceRequest(BaseModel):
    system_prompt: str
    model: str
    temperature: float
    max_tokens: int

class DeleteSystemPromptRequest(BaseModel):
    system_prompt: str

class DeleteResponse(BaseModel):
    success: bool
    deleted: int = 0
    error: str | None = None