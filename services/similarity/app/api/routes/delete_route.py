from fastapi import APIRouter
from app.models.schemas import (
    DeleteNamespaceRequest,
    DeleteResponse,
    DeleteSystemPromptRequest,
)
from app.cache.key import build_namespace, hash_system_prompt
from app.store.vector import (
    clear_keys_by_model,
    clear_keys_by_namespace,
    clear_keys_by_prefix,
    clear_keys_by_system_prompt_hash,
)

router = APIRouter(prefix="/delete", tags=["delete"])


@router.delete("/namespace", response_model=DeleteResponse)
async def delete_namespace(request: DeleteNamespaceRequest):
    namespace = build_namespace(
        request.system_prompt, request.model, request.temperature, request.max_tokens
    )
    try:
        deleted = await clear_keys_by_namespace(namespace)
        return DeleteResponse(success=True, deleted=deleted)
    except Exception as e:
        return DeleteResponse(success=False, deleted=0, error=str(e))


@router.delete("/system-prompt", response_model=DeleteResponse)
async def delete_system_prompt(request: DeleteSystemPromptRequest):
    try:
        deleted = await clear_keys_by_system_prompt_hash(
            hash_system_prompt(request.system_prompt)
        )
        return DeleteResponse(success=True, deleted=deleted)
    except Exception as e:
        return DeleteResponse(success=False, deleted=0, error=str(e))


@router.delete("/model", response_model=DeleteResponse)
async def delete_model(model: str):
    try:
        deleted = await clear_keys_by_model(model)
        return DeleteResponse(success=True, deleted=deleted)
    except Exception as e:
        return DeleteResponse(success=False, deleted=0, error=str(e))


@router.delete("/prefix", response_model=DeleteResponse)
async def delete_prefix(prefix: str):
    try:
        deleted = await clear_keys_by_prefix(prefix)
        return DeleteResponse(success=True, deleted=deleted)
    except Exception as e:
        return DeleteResponse(success=False, deleted=0, error=str(e))
