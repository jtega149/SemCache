from openai import AsyncOpenAI
from app.config import settings

_client: AsyncOpenAI | None = None

def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


async def embed(text: str) -> list[float]:
    client = get_client()
    response = await client.embeddings.create(
        model=settings.embedding_model,
        input=text,
        dimensions=384,
    )
    return response.data[0].embedding
