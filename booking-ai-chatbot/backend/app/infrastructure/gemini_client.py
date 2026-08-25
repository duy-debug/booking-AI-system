"""Application port and data models for language model interaction."""
# ruff: noqa: E402

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol


class LLMGatewayError(Exception):
    """Base exception for expected language-model provider failures."""


class LLMGatewayTimeoutError(LLMGatewayError):
    """Raised when the language-model provider times out."""


class LLMGatewayUnavailableError(LLMGatewayError):
    """Raised when the configured language-model provider is unavailable."""


class InvalidLLMResponseError(LLMGatewayError):
    """Raised when a provider response violates the gateway contract."""


@dataclass(frozen=True, slots=True)
class LLMMessage:
    """Represents a message sent to a language model."""

    role: str
    content: str


@dataclass(frozen=True, slots=True)
class LLMToolCall:
    """Represents a parsed tool call returned by a language model."""

    name: str
    arguments: dict[str, object]


@dataclass(frozen=True, slots=True)
class LLMResponse:
    """Represents text and tool calls returned by a language model."""

    content: str | None = None
    tool_calls: tuple[LLMToolCall, ...] = ()


class LLMGateway(Protocol):
    """Defines language model generation required by the application."""

    async def generate(
        self,
        messages: list[LLMMessage],
        *,
        tools: list[dict[str, object]] | None = None,
    ) -> LLMResponse:
        """Generate a response from prepared messages and optional tools."""
        ...

    def stream_generate(
        self,
        messages: list[LLMMessage],
        *,
        tools: list[dict[str, object]] | None = None,
    ) -> AsyncIterator[str]:
        """Stream response text chunks from prepared messages and optional tools."""
        ...


"""Gemini adapter implementing the OpenAI-compatible language-model port."""

import json
import logging
from time import perf_counter

import httpx

from app.infrastructure.context_store import elapsed_ms, record_turn_metrics, trace_log

_LOGGER = logging.getLogger(__name__)


class GeminiClient:
    """Generate text through Gemini's OpenAI-compatible chat endpoint."""

    # Cấu hình Gemini/OpenAI-compatible endpoint, model chính và model fallback nếu có.
    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        api_key: str | None,
        base_url: str,
        model: str,
        fallback_model: str | None = None,
        max_retries: int = 0,
    ) -> None:
        normalized_api_key = api_key.strip() if api_key else ""
        self._client = client
        self._api_key = normalized_api_key or None
        self._base_url = base_url.strip().rstrip("/")
        self._model = model.strip()
        normalized_fallback = fallback_model.strip() if fallback_model else ""
        self._fallback_model = normalized_fallback or None
        self._max_retries = max_retries

    # Gửi chat completion tới Gemini và fallback model khi lỗi quota/rate-limit phù hợp.
    async def generate(
        self,
        messages: list[LLMMessage],
        *,
        tools: list[dict[str, object]] | None = None,
    ) -> LLMResponse:
        """Return a provider response, with one configured transient failover."""
        started_at = perf_counter()
        if self._api_key is None:
            self._log_failure("gemini_not_configured", started_at, self._model, 1)
            raise LLMGatewayUnavailableError("Gemini is not configured.")
        models = [self._model]
        if (
            self._max_retries == 1
            and self._fallback_model is not None
            and self._fallback_model != self._model
        ):
            models.append(self._fallback_model)

        for attempt, model in enumerate(models, start=1):
            attempt_started_at = perf_counter()
            trace_log(
                _LOGGER,
                logging.DEBUG,
                "LLMUsage",
                "request",
                provider="gemini",
                model=model,
                operation="chat_completion",
                function="complete",
                attempt=attempt,
                input_summary={
                    "message_count": len(messages),
                    "character_count": sum(len(message.content) for message in messages),
                    "tools_enabled": tools is not None,
                },
                status="started",
            )
            payload: dict[str, object] = {
                "model": model,
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
                error_code = "gemini_timeout"
                self._log_failure(error_code, attempt_started_at, model, attempt)
                if attempt < len(models):
                    self._log_fallback(model, models[attempt], error_code)
                    continue
                raise LLMGatewayTimeoutError("Gemini timed out.") from error
            except httpx.HTTPStatusError as error:
                status_code = error.response.status_code
                error_code = _http_error_code(status_code)
                self._log_failure(error_code, attempt_started_at, model, attempt)
                if attempt < len(models) and _is_fallback_status(status_code):
                    self._log_fallback(model, models[attempt], error_code)
                    continue
                raise LLMGatewayUnavailableError("Gemini is unavailable.") from error
            except httpx.HTTPError as error:
                error_code = "gemini_unavailable"
                self._log_failure(error_code, attempt_started_at, model, attempt)
                if attempt < len(models):
                    self._log_fallback(model, models[attempt], error_code)
                    continue
                raise LLMGatewayUnavailableError("Gemini is unavailable.") from error
            try:
                parsed = _parse_response(response)
            except InvalidLLMResponseError:
                self._log_failure("gemini_invalid_response", attempt_started_at, model, attempt)
                raise
            prompt_tokens, completion_tokens = _usage_tokens(response)
            fields: dict[str, object] = {
                "provider": "gemini",
                "model": model,
                "operation": "chat_completion",
                "attempt": attempt,
                "duration_ms": elapsed_ms(started_at),
            }
            if prompt_tokens is not None:
                fields["input_tokens"] = prompt_tokens
            if completion_tokens is not None:
                fields["output_tokens"] = completion_tokens
            if prompt_tokens is not None and completion_tokens is not None:
                fields["total_tokens"] = prompt_tokens + completion_tokens
            record_turn_metrics(
                llm_calls=1,
                llm_input_tokens=prompt_tokens,
                llm_output_tokens=completion_tokens,
            )
            trace_log(_LOGGER, logging.INFO, "LLMUsage", "completed", **fields)
            return parsed
        raise LLMGatewayUnavailableError("Gemini is unavailable.")

    # Stream chat completion theo OpenAI-compatible SSE để frontend render token dần.
    async def stream_generate(
        self,
        messages: list[LLMMessage],
        *,
        tools: list[dict[str, object]] | None = None,
    ) -> AsyncIterator[str]:
        """Yield provider response chunks, with the same fallback behavior as generate()."""
        started_at = perf_counter()
        if self._api_key is None:
            self._log_failure("gemini_not_configured", started_at, self._model, 1)
            raise LLMGatewayUnavailableError("Gemini is not configured.")
        models = [self._model]
        if (
            self._max_retries == 1
            and self._fallback_model is not None
            and self._fallback_model != self._model
        ):
            models.append(self._fallback_model)

        for attempt, model in enumerate(models, start=1):
            attempt_started_at = perf_counter()
            payload: dict[str, object] = {
                "model": model,
                "messages": [
                    {"role": message.role, "content": message.content} for message in messages
                ],
                "stream": True,
            }
            if tools is not None:
                payload["tools"] = tools
            trace_log(
                _LOGGER,
                logging.DEBUG,
                "LLMUsage",
                "request",
                provider="gemini",
                model=model,
                operation="chat_completion_stream",
                function="stream_complete",
                attempt=attempt,
                input_summary={
                    "message_count": len(messages),
                    "character_count": sum(len(message.content) for message in messages),
                    "tools_enabled": tools is not None,
                },
                status="started",
            )
            try:
                async with self._client.stream(
                    "POST",
                    f"{self._base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=payload,
                ) as response:
                    response.raise_for_status()
                    record_turn_metrics(llm_calls=1)
                    async for line in response.aiter_lines():
                        stream_data = _stream_data(line)
                        if stream_data is None:
                            continue
                        if stream_data == "[DONE]":
                            break
                        delta = _parse_stream_delta(stream_data)
                        if delta:
                            yield delta
                    trace_log(
                        _LOGGER,
                        logging.INFO,
                        "LLMUsage",
                        "completed",
                        provider="gemini",
                        model=model,
                        operation="chat_completion_stream",
                        attempt=attempt,
                        duration_ms=elapsed_ms(started_at),
                    )
                    return
            except httpx.TimeoutException as error:
                error_code = "gemini_timeout"
                self._log_failure(error_code, attempt_started_at, model, attempt)
                if attempt < len(models):
                    self._log_fallback(model, models[attempt], error_code)
                    continue
                raise LLMGatewayTimeoutError("Gemini timed out.") from error
            except httpx.HTTPStatusError as error:
                status_code = error.response.status_code
                error_code = _http_error_code(status_code)
                self._log_failure(error_code, attempt_started_at, model, attempt)
                if attempt < len(models) and _is_fallback_status(status_code):
                    self._log_fallback(model, models[attempt], error_code)
                    continue
                raise LLMGatewayUnavailableError("Gemini is unavailable.") from error
            except httpx.HTTPError as error:
                error_code = "gemini_unavailable"
                self._log_failure(error_code, attempt_started_at, model, attempt)
                if attempt < len(models):
                    self._log_fallback(model, models[attempt], error_code)
                    continue
                raise LLMGatewayUnavailableError("Gemini is unavailable.") from error
            except InvalidLLMResponseError:
                self._log_failure("gemini_invalid_response", attempt_started_at, model, attempt)
                raise
        raise LLMGatewayUnavailableError("Gemini is unavailable.")

    # Log lỗi LLM an toàn, không ghi API key hoặc raw payload.
    def _log_failure(
        self,
        error_code: str,
        started_at: float,
        model: str,
        attempt: int,
    ) -> None:
        trace_log(
            _LOGGER,
            logging.WARNING,
            "LLMUsage",
            "failed",
            provider="gemini",
            model=model,
            operation="chat_completion",
            attempt=attempt,
            error_code=error_code,
            duration_ms=elapsed_ms(started_at),
        )

    # Log lần chuyển sang fallback model để debug quota/provider failure.
    def _log_fallback(
        self,
        primary_model: str,
        fallback_model: str,
        reason: str,
    ) -> None:
        trace_log(
            _LOGGER,
            logging.WARNING,
            "LLMUsage",
            "fallback_activated",
            provider="gemini",
            operation="chat_completion",
            primary_model=primary_model,
            fallback_model=fallback_model,
            reason=reason,
        )


# Map HTTP status từ Gemini thành error code ổn định cho log/recovery.
def _http_error_code(status_code: int) -> str:
    if status_code in {401, 403}:
        return "gemini_auth_failed"
    if status_code == 429:
        return "gemini_rate_limited"
    return "gemini_unavailable"


# Xác định status có nên thử fallback model hay không.
def _is_fallback_status(status_code: int) -> bool:
    return status_code in {408, 429} or status_code >= 500


# Lấy usage token thật từ provider nếu response có trả metadata usage.
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


# Parse Gemini/OpenAI-compatible response thành LLMResponse nội bộ.
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


# Lấy payload `data:` từ SSE line của provider, bỏ qua keep-alive/comment line.
def _stream_data(line: str) -> str | None:
    if not line.startswith("data:"):
        return None
    payload = line.removeprefix("data:").strip()
    return payload or None


# Parse một delta chunk từ OpenAI-compatible streaming payload.
def _parse_stream_delta(payload: str) -> str | None:
    try:
        body = json.loads(payload)
        delta = body["choices"][0].get("delta", {})
        content = delta.get("content")
        if content is None:
            return None
        if not isinstance(content, str):
            raise TypeError
        return content
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
        raise InvalidLLMResponseError("Gemini returned an invalid streaming response.") from error


# Parse một tool/function call từ provider để NLU dùng structured candidates.
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
