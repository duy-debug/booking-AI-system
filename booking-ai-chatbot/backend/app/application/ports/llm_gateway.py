"""Application port and data models for language model interaction."""

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
