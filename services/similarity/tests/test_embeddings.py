from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.config import settings
from app.embeddings.openai import embed


async def test_embed_returns_vector():
    """ Runs embed() without hitting the OpenAI API """
    fake_vector = [0.1] * 384
    fake_response = SimpleNamespace(
        data=[SimpleNamespace(embedding=fake_vector)]
    )
    mock_create = AsyncMock(return_value=fake_response)
    mock_client = SimpleNamespace(
        embeddings=SimpleNamespace(create=mock_create)
    )

    with patch("app.embeddings.openai.get_client", return_value=mock_client):
        result = await embed("What is Python?")

    assert result == fake_vector
    mock_create.assert_awaited_once()
    assert mock_create.await_args.kwargs["model"] == settings.embedding_model
    assert mock_create.await_args.kwargs["input"] == "What is Python?"
