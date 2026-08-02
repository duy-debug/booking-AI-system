"""Unit tests for the OpenRouter language-model gateway adapter."""

import json

import httpx
import pytest

from app.application.ports.llm_gateway import (
    InvalidLLMResponseError,
    LLMGatewayTimeoutError,
    LLMGatewayUnavailableError,
    LLMMessage,
)
from app.infrastructure.llm.openrouter_llm_gateway import OpenRouterLLMGateway


def gateway(
    handler: httpx.MockTransport,
    *,
    api_key: str | None = "secret-key",
) -> tuple[httpx.AsyncClient, OpenRouterLLMGateway]:
    client = httpx.AsyncClient(transport=handler)
    return client, OpenRouterLLMGateway(
        client=client,
        api_key=api_key,
        base_url="https://openrouter.test/api/v1/",
        model="test-model",
    )


@pytest.mark.asyncio
async def test_generate_sends_messages_once_and_parses_content() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            request=request,
            json={"choices": [{"message": {"content": '{"intent":"confirm"}'}}]},
        )

    client, adapter = gateway(httpx.MockTransport(handler))
    result = await adapter.generate([LLMMessage("user", "confirm this")])

    assert result.content == '{"intent":"confirm"}'
    assert len(requests) == 1
    assert requests[0].url == "https://openrouter.test/api/v1/chat/completions"
    assert requests[0].headers["authorization"] == "Bearer secret-key"
    assert json.loads(requests[0].content) == {
        "model": "test-model",
        "messages": [{"role": "user", "content": "confirm this"}],
    }
    await client.aclose()


@pytest.mark.asyncio
async def test_generate_parses_tool_calls_when_present() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            json={
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "function": {
                                        "name": "search",
                                        "arguments": '{"query":"Tokyo"}',
                                    }
                                }
                            ],
                        }
                    }
                ]
            },
        )

    client, adapter = gateway(httpx.MockTransport(handler))
    result = await adapter.generate([LLMMessage("user", "search")])

    assert result.tool_calls[0].name == "search"
    assert result.tool_calls[0].arguments == {"query": "Tokyo"}
    await client.aclose()


@pytest.mark.asyncio
async def test_unconfigured_gateway_fails_without_http_request() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(500, request=request)

    client, adapter = gateway(httpx.MockTransport(handler), api_key=None)

    with pytest.raises(LLMGatewayUnavailableError):
        await adapter.generate([LLMMessage("user", "message")])

    assert requests == []
    await client.aclose()


@pytest.mark.asyncio
async def test_timeout_and_http_failure_are_typed() -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=request)

    timeout_client, timeout_adapter = gateway(httpx.MockTransport(timeout))
    with pytest.raises(LLMGatewayTimeoutError):
        await timeout_adapter.generate([LLMMessage("user", "message")])
    await timeout_client.aclose()

    def unavailable(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, request=request)

    unavailable_client, unavailable_adapter = gateway(
        httpx.MockTransport(unavailable)
    )
    with pytest.raises(LLMGatewayUnavailableError):
        await unavailable_adapter.generate([LLMMessage("user", "message")])
    await unavailable_client.aclose()


@pytest.mark.asyncio
async def test_invalid_provider_shape_is_typed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, request=request, json={"choices": []})

    client, adapter = gateway(httpx.MockTransport(handler))

    with pytest.raises(InvalidLLMResponseError):
        await adapter.generate([LLMMessage("user", "message")])

    await client.aclose()
