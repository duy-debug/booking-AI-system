"""Encode deterministic, JSON-backed Server-Sent Events."""

import json
import re
from collections.abc import Mapping
from enum import StrEnum

_EVENT_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*$")


class SSEEventType(StrEnum):
    """Names the business-level events emitted by the chat stream."""

    STARTED = "started"
    MESSAGE = "message"
    COMPLETED = "completed"
    ERROR = "error"


class InvalidSSEEventError(ValueError):
    """Raised when an SSE event name or data object is invalid."""


class SSESerializationError(TypeError):
    """Raised when an SSE data object is not JSON serializable."""


def encode_sse_event(
    *,
    event: str,
    data: Mapping[str, object],
) -> str:
    """Return one compact SSE frame containing a JSON object."""
    if not isinstance(event, str) or not _EVENT_NAME_PATTERN.fullmatch(event):
        raise InvalidSSEEventError("SSE event name is invalid.")
    if not isinstance(data, Mapping):
        raise InvalidSSEEventError("SSE data must be a mapping.")
    try:
        payload = json.dumps(
            dict(data),
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise SSESerializationError("SSE data must be JSON serializable.") from error
    return f"event: {event}\ndata: {payload}\n\n"
