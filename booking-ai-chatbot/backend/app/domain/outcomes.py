"""Typed outcomes returned by application handlers."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType


class HandlerOutcome(StrEnum):
    """Stable outcomes consumed by the dialog workflow."""

    SUCCESS = "success"
    INVALID_INPUT = "invalid_input"
    NOT_FOUND = "not_found"
    AMBIGUOUS = "ambiguous"
    NO_SLOTS = "no_slots"
    CONFLICT = "conflict"
    BLOCKED = "blocked"
    EXTERNAL_FAILURE = "external_failure"


@dataclass(frozen=True, slots=True)
class HandlerResult:
    """Normalized handler output without response text or state transitions."""

    outcome: HandlerOutcome
    data: Mapping[str, object] = field(default_factory=dict)
    context_updates: Mapping[str, object] = field(default_factory=dict)
    error_code: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "data", MappingProxyType(dict(self.data)))
        object.__setattr__(
            self,
            "context_updates",
            MappingProxyType(dict(self.context_updates)),
        )
