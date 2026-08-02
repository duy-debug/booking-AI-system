"""OpenRouter adapter implementing the language-model application port."""

import json

import httpx

from app.application.ports.llm_gateway import (
    InvalidLLMResponseError,
    LLMGatewayTimeoutError,
    LLMGatewayUnavailableError,
    LLMMessage,
    LLMResponse,
    LLMToolCall,
)


class OpenRouterLLMGateway:
    """Generate text through OpenRouter using an injected HTTP client."""

    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        api_key: str | None,
        base_url: str,
        model: str,
    ) -> None:
        self._client = client
        self._api_key = api_key.strip() if api_key else None
        self._base_url = base_url.rstrip("/")
        self._model = model.strip()

    async def generate(
        self,
        messages: list[LLMMessage],
        *,
        tools: list[dict[str, object]] | None = None,
    ) -> LLMResponse:
        """Return one provider response without retry or failover."""
        if self._api_key is None:
            raise LLMGatewayUnavailableError("LLM provider is not configured.")
        payload: dict[str, object] = {
            "model": self._model,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in messages
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
            raise LLMGatewayTimeoutError("LLM provider timed out.") from error
        except httpx.HTTPError as error:
            raise LLMGatewayUnavailableError("LLM provider is unavailable.") from error
        return _parse_response(response)


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
        raise InvalidLLMResponseError("LLM provider returned an invalid response.") from error
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
