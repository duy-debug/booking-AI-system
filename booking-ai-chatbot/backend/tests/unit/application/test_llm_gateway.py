"""Contract tests for the language model gateway port."""

from dataclasses import FrozenInstanceError
from typing import TYPE_CHECKING

import pytest

from app.application.ports.llm_gateway import (
    LLMGateway,
    LLMMessage,
    LLMResponse,
    LLMToolCall,
)

MESSAGE = LLMMessage(role="user", content="Book an appointment")
TOOL_CALL = LLMToolCall(
    name="search_shops",
    arguments={"query": "central"},
)
TOOLS: list[dict[str, object]] = [
    {
        "name": "search_shops",
        "description": "Search for shops",
    }
]


class FakeLLMGateway:
    """In-memory fake implementing the language model gateway contract."""

    def __init__(self) -> None:
        self.received_messages: list[LLMMessage] | None = None
        self.received_tools: list[dict[str, object]] | None = None

    async def generate(
        self,
        messages: list[LLMMessage],
        *,
        tools: list[dict[str, object]] | None = None,
    ) -> LLMResponse:
        self.received_messages = messages
        self.received_tools = tools
        return LLMResponse(tool_calls=(TOOL_CALL,))


class IncompleteLLMGateway:
    """Fake that intentionally does not satisfy the gateway protocol."""


if TYPE_CHECKING:
    valid_gateway: LLMGateway = FakeLLMGateway()
    invalid_gateway: LLMGateway = IncompleteLLMGateway()  # type: ignore[assignment]


def use_llm_gateway(gateway: LLMGateway) -> LLMGateway:
    """Accept the abstraction consumed by dialog components."""
    return gateway


def test_create_llm_message() -> None:
    assert MESSAGE.role == "user"
    assert MESSAGE.content == "Book an appointment"


def test_llm_message_is_immutable() -> None:
    with pytest.raises(FrozenInstanceError):
        MESSAGE.content = "Changed"  # type: ignore[misc]


def test_llm_messages_with_same_data_are_equal() -> None:
    assert MESSAGE == LLMMessage(role="user", content="Book an appointment")


def test_create_llm_tool_call_with_name_and_arguments() -> None:
    assert TOOL_CALL.name == "search_shops"
    assert TOOL_CALL.arguments == {"query": "central"}


def test_create_content_only_llm_response() -> None:
    response = LLMResponse(content="How can I help?")

    assert response.content == "How can I help?"
    assert response.tool_calls == ()


def test_create_tool_call_only_llm_response() -> None:
    response = LLMResponse(tool_calls=(TOOL_CALL,))

    assert response.content is None
    assert response.tool_calls == (TOOL_CALL,)


def test_llm_response_defaults() -> None:
    response = LLMResponse()

    assert response.content is None
    assert response.tool_calls == ()


def test_llm_response_is_immutable() -> None:
    response = LLMResponse(content="Original")

    with pytest.raises(FrozenInstanceError):
        response.content = "Changed"  # type: ignore[misc]


def test_complete_fake_is_accepted_as_llm_gateway() -> None:
    gateway = use_llm_gateway(FakeLLMGateway())

    assert isinstance(gateway, FakeLLMGateway)


@pytest.mark.asyncio
async def test_fake_generate_receives_inputs_and_returns_llm_response() -> None:
    fake = FakeLLMGateway()
    gateway: LLMGateway = fake
    messages = [MESSAGE]

    response = await gateway.generate(messages, tools=TOOLS)

    assert fake.received_messages == messages
    assert fake.received_tools == TOOLS
    assert isinstance(response, LLMResponse)
    assert response.tool_calls == (TOOL_CALL,)
