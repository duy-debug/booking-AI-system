from unittest.mock import MagicMock, patch

import pytest

from app.conversation.chain import GENERAL_SYSTEM_PROMPT, answer_general
from app.core.exceptions import AppError
from app.core.token_stream import reset_token_emitter, set_token_emitter


@pytest.mark.asyncio
async def test_answer_general_uses_llm_without_rag() -> None:
    client = MagicMock()
    response = MagicMock()
    response.choices = [MagicMock(message=MagicMock(content="Chào bạn, mình là Kori!"))]
    client.chat.completions.create.return_value = response

    with patch("app.conversation.chain.get_groq_client", return_value=client):
        answer = await answer_general("Xin chào")

    assert answer == "Chào bạn, mình là Kori!"
    request = client.chat.completions.create.call_args.kwargs
    assert request["messages"][0]["content"] == GENERAL_SYSTEM_PROMPT
    assert request["messages"][1]["content"] == "Xin chào"


@pytest.mark.asyncio
async def test_answer_general_maps_provider_failure() -> None:
    client = MagicMock()
    client.chat.completions.create.side_effect = RuntimeError("provider down")

    with (
        patch("app.conversation.chain.get_groq_client", return_value=client),
        pytest.raises(AppError) as exc,
    ):
        await answer_general("Hello")

    assert exc.value.code == "LLM_UNAVAILABLE"


@pytest.mark.asyncio
async def test_answer_general_streams_provider_deltas() -> None:
    client = MagicMock()
    first = MagicMock()
    first.choices = [MagicMock(delta=MagicMock(content="Xin "))]
    second = MagicMock()
    second.choices = [MagicMock(delta=MagicMock(content="chào"))]
    client.chat.completions.create.return_value = iter([first, second])
    deltas: list[str] = []

    context_token = set_token_emitter(deltas.append)
    try:
        with patch("app.conversation.chain.get_groq_client", return_value=client):
            answer = await answer_general("Hello")
    finally:
        reset_token_emitter(context_token)

    assert answer == "Xin chào"
    assert deltas == ["Xin ", "chào"]
    assert client.chat.completions.create.call_args.kwargs["stream"] is True
