"""Gemini adapter implementing the OpenAI-compatible language-model port."""

import json
import logging
from time import perf_counter

import httpx

from app.application.ports.llm_gateway import (
    InvalidLLMResponseError,
    LLMGatewayTimeoutError,
    LLMGatewayUnavailableError,
    LLMMessage,
    LLMResponse,
    LLMToolCall,
)
from app.core.logging import elapsed_ms, trace_log

_LOGGER = logging.getLogger(__name__)


class GeminiLLMGateway:
    """Generate text through Gemini's OpenAI-compatible chat endpoint."""

    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        api_key: str | None,
        base_url: str,
        model: str,
    ) -> None:
        normalized_api_key = api_key.strip() if api_key else ""
        self._client = client
        self._api_key = normalized_api_key or None
        self._base_url = base_url.strip().rstrip("/")
        self._model = model.strip()

    async def generate(
        self,
        messages: list[LLMMessage],
        *,
        tools: list[dict[str, object]] | None = None,
    ) -> LLMResponse:
        """Return one provider response without retry or failover."""
        started_at = perf_counter()
        if self._api_key is None:
            self._log_failure("gemini_not_configured", started_at)
            raise LLMGatewayUnavailableError("Gemini is not configured.")
        payload: dict[str, object] = {
            "model": self._model,
            "messages": [
                {"role": message.role, "content": message.content} for message in messages
            ],
        }
        if tools is not None:
            payload["tools"] = tools
        try:
            response = await self._client.post(
                f"{self._base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=payload,
            )
            response.raise_for_status()
        except httpx.TimeoutException as error:
            self._log_failure("gemini_timeout", started_at)
            raise LLMGatewayTimeoutError("Gemini timed out.") from error
        except httpx.HTTPStatusError as error:
            error_code = _http_error_code(error.response.status_code)
            self._log_failure(error_code, started_at)
            raise LLMGatewayUnavailableError("Gemini is unavailable.") from error
        except httpx.HTTPError as error:
            self._log_failure("gemini_unavailable", started_at)
            raise LLMGatewayUnavailableError("Gemini is unavailable.") from error
        try:
            parsed = _parse_response(response)
        except InvalidLLMResponseError:
            self._log_failure("gemini_invalid_response", started_at)
            raise
        prompt_tokens, completion_tokens = _usage_tokens(response)
        fields: dict[str, object] = {
            "provider": "gemini",
            "model": self._model,
            "operation": "chat_completion",
            "duration_ms": elapsed_ms(started_at),
        }
        if prompt_tokens is not None:
            fields["input_tokens"] = prompt_tokens
        if completion_tokens is not None:
            fields["output_tokens"] = completion_tokens
        trace_log(_LOGGER, logging.INFO, "LLMUsage", "completed", **fields)
        return parsed

    def _log_failure(self, error_code: str, started_at: float) -> None:
        trace_log(
            _LOGGER,
            logging.WARNING,
            "LLMUsage",
            "failed",
            provider="gemini",
            model=self._model,
            operation="chat_completion",
            error_code=error_code,
            duration_ms=elapsed_ms(started_at),
        )


def _http_error_code(status_code: int) -> str:
    if status_code in {401, 403}:
        return "gemini_auth_failed"
    if status_code == 429:
        return "gemini_rate_limited"
    return "gemini_unavailable"


def _usage_tokens(response: httpx.Response) -> tuple[int | None, int | None]:
    try:
        usage = response.json().get("usage", {})
    except (ValueError, AttributeError):
        return None, None
    if not isinstance(usage, dict):
        return None, None
    prompt = usage.get("prompt_tokens")
    completion = usage.get("completion_tokens")
    return (
        prompt if type(prompt) is int and prompt >= 0 else None,
        completion if type(completion) is int and completion >= 0 else None,
    )


def _parse_response(response: httpx.Response) -> LLMResponse:
    try:
        body = response.json()
        message = body["choices"][0]["message"]
        content = message.get("content")
        raw_tool_calls = message.get("tool_calls", [])
        if content is not None and not isinstance(content, str):
            raise TypeError
        tool_calls = tuple(_parse_tool_call(value) for value in raw_tool_calls)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
        raise InvalidLLMResponseError("Gemini returned an invalid response.") from error
    return LLMResponse(content=content, tool_calls=tool_calls)


def _parse_tool_call(value: object) -> LLMToolCall:
    if not isinstance(value, dict):
        raise TypeError
    function = value["function"]
    if not isinstance(function, dict):
        raise TypeError
    name = function["name"]
    arguments = function["arguments"]
    if not isinstance(name, str) or not isinstance(arguments, str):
        raise TypeError
    parsed_arguments = json.loads(arguments)
    if not isinstance(parsed_arguments, dict):
        raise TypeError
    return LLMToolCall(name=name, arguments=parsed_arguments)
