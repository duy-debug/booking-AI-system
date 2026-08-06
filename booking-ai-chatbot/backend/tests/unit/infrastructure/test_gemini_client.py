"""Unit tests for the Gemini OpenAI-compatible gateway."""

import json
import logging

import httpx
import pytest

from app.infrastructure.gemini_client import (
    GeminiClient,
    InvalidLLMResponseError,
    LLMGatewayTimeoutError,
    LLMGatewayUnavailableError,
    LLMMessage,
)

BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


def gateway(
    handler: httpx.MockTransport,
    *,
    api_key: str | None = "secret-key",
    model: str = "gemini-2.5-flash",
) -> tuple[httpx.AsyncClient, GeminiClient]:
    client = httpx.AsyncClient(transport=handler)
    return client, GeminiClient(
        client=client,
        api_key=api_key,
        base_url=BASE_URL,
        model=model,
    )


@pytest.mark.asyncio
async def test_generate_uses_injected_model_endpoint_and_parses_structured_content() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            request=request,
            json={"choices": [{"message": {"content": '{"intent":"confirm"}'}}]},
        )

    client, adapter = gateway(httpx.MockTransport(handler), model=" injected-model ")
    result = await adapter.generate([LLMMessage("user", "confirm this")])

    assert result.content == '{"intent":"confirm"}'
    assert len(requests) == 1
    assert str(requests[0].url) == f"{BASE_URL}chat/completions"
    assert requests[0].headers["authorization"] == "Bearer secret-key"
    assert json.loads(requests[0].content) == {
        "model": "injected-model",
        "messages": [{"role": "user", "content": "confirm this"}],
    }
    await client.aclose()


@pytest.mark.asyncio
async def test_generate_parses_openai_compatible_tool_calls() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            json={"choices": [{"message": {"content": None, "tool_calls": [{
                "function": {"name": "extract_intent", "arguments": '{"intent":"faq"}'},
            }]}}]},
        )

    client, adapter = gateway(httpx.MockTransport(handler))
    result = await adapter.generate([LLMMessage("user", "question")])

    assert result.tool_calls[0].name == "extract_intent"
    assert result.tool_calls[0].arguments == {"intent": "faq"}
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("api_key", [None, "", "   \t"])
async def test_missing_or_blank_key_is_gemini_not_configured(
    api_key: str | None,
    caplog: pytest.LogCaptureFixture,
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(500, request=request)

    client, adapter = gateway(httpx.MockTransport(handler), api_key=api_key)
    with caplog.at_level(logging.WARNING):
        with pytest.raises(LLMGatewayUnavailableError):
            await adapter.generate([LLMMessage("user", "message")])

    assert requests == []
    assert "gemini_not_configured" in caplog.text
    assert "openrouter" not in caplog.text.casefold()
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "error_code"),
    [(401, "gemini_auth_failed"), (403, "gemini_auth_failed"), (429, "gemini_rate_limited")],
)
async def test_provider_status_is_typed_and_safely_logged(
    status_code: int,
    error_code: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = "api-key-that-must-never-be-logged"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, request=request, json={"error": "provider error"})

    client, adapter = gateway(httpx.MockTransport(handler), api_key=secret)
    with caplog.at_level(logging.WARNING):
        with pytest.raises(LLMGatewayUnavailableError):
            await adapter.generate([LLMMessage("user", "message")])

    assert error_code in caplog.text
    assert secret not in caplog.text
    await client.aclose()


@pytest.mark.asyncio
async def test_timeout_is_typed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=request)

    client, adapter = gateway(httpx.MockTransport(handler))
    with pytest.raises(LLMGatewayTimeoutError):
        await adapter.generate([LLMMessage("user", "message")])
    await client.aclose()


@pytest.mark.asyncio
async def test_malformed_response_is_typed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, request=request, json={"choices": []})

    client, adapter = gateway(httpx.MockTransport(handler))
    with pytest.raises(InvalidLLMResponseError):
        await adapter.generate([LLMMessage("user", "message")])
    await client.aclose()


@pytest.mark.asyncio
async def test_usage_is_logged_only_when_returned(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            json={
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"prompt_tokens": 7, "completion_tokens": 3},
            },
        )

    client, adapter = gateway(httpx.MockTransport(handler))
    with caplog.at_level(logging.INFO):
        await adapter.generate([LLMMessage("user", "message")])

    assert "input_tokens=7" in caplog.text
    assert "output_tokens=3" in caplog.text
    await client.aclose()
