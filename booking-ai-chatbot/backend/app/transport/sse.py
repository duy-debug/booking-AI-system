"""Encode deterministic, JSON-backed Server-Sent Events."""

import asyncio
import json
import logging
import re
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from enum import StrEnum
from time import perf_counter
from typing import TYPE_CHECKING

from app.infrastructure.context_store import (
    bind_trace_context,
    elapsed_ms,
    reset_trace_context,
    trace_log,
)

if TYPE_CHECKING:
    from app.dependencies import ApplicationContainer
    from app.dialog.instruction_builder import DialogResponse
    from app.transport.schemas import ChatRequest, ChatResponse

ProcessMessage = Callable[..., Awaitable["DialogResponse"]]
ResponseMapper = Callable[[str, "DialogResponse"], "ChatResponse"]

logger = logging.getLogger(__name__)

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


async def stream_chat_events(
    *,
    request: "ChatRequest",
    container: "ApplicationContainer",
    process_message: ProcessMessage,
    response_mapper: ResponseMapper,
    correlation_id: str | None = None,
) -> AsyncIterator[str]:
    """Generate the complete SSE lifecycle around one controller call."""
    token = bind_trace_context(
        trace_id=correlation_id,
        session_id=request.conversation_id,
    )
    try:
        async for event in _stream_bound_chat_events(
            request=request,
            container=container,
            process_message=process_message,
            response_mapper=response_mapper,
            correlation_id=correlation_id,
        ):
            yield event
    finally:
        reset_trace_context(token)


async def _stream_bound_chat_events(
    *,
    request: "ChatRequest",
    container: "ApplicationContainer",
    process_message: ProcessMessage,
    response_mapper: ResponseMapper,
    correlation_id: str | None,
) -> AsyncIterator[str]:
    started_at = perf_counter()
    chunk_count = 0
    bytes_sent = 0
    completed = False
    trace_log(logger, logging.INFO, "SSETransport", "sse_started")
    started_event = encode_sse_event(
        event=SSEEventType.STARTED,
        data={"conversation_id": request.conversation_id},
    )
    chunk_count += 1
    bytes_sent += len(started_event.encode("utf-8"))
    yield started_event

    try:
        kwargs: dict[str, object] = {"request": request, "container": container}
        if correlation_id is not None:
            kwargs["correlation_id"] = correlation_id
        dialog_response = await process_message(**kwargs)
        response = response_mapper(request.conversation_id, dialog_response)
        message_event = encode_sse_event(
            event=SSEEventType.MESSAGE,
            data=response.model_dump(mode="json"),
        )
        completed_event = encode_sse_event(
            event=SSEEventType.COMPLETED,
            data={
                "conversation_id": request.conversation_id,
                "stream_status": "completed",
                "dialog_status": response.status,
            },
        )
    except asyncio.CancelledError:
        trace_log(
            logger,
            logging.WARNING,
            "SSETransport",
            "sse_client_disconnected",
            chunks_sent=chunk_count,
            duration_ms=elapsed_ms(started_at),
        )
        raise
    except Exception:
        error_event = encode_sse_event(
            event=SSEEventType.ERROR,
            data={
                "conversation_id": request.conversation_id,
                "code": "chat_processing_failed",
                "message": "Hệ thống chưa thể xử lý yêu cầu lúc này.",
            },
        )
        chunk_count += 1
        bytes_sent += len(error_event.encode("utf-8"))
        yield error_event
        completed = True
        trace_log(
            logger,
            logging.WARNING,
            "SSETransport",
            "sse_completed",
            chunk_count=chunk_count,
            bytes_sent=bytes_sent,
            duration_ms=elapsed_ms(started_at),
            status="error",
        )
        return

    try:
        for event in (message_event, completed_event):
            chunk_count += 1
            bytes_sent += len(event.encode("utf-8"))
            yield event
        completed = True
        trace_log(
            logger,
            logging.INFO,
            "SSETransport",
            "sse_completed",
            chunk_count=chunk_count,
            bytes_sent=bytes_sent,
            duration_ms=elapsed_ms(started_at),
            client_disconnected=False,
        )
    except (asyncio.CancelledError, GeneratorExit):
        completed = True
        trace_log(
            logger,
            logging.WARNING,
            "SSETransport",
            "sse_client_disconnected",
            chunks_sent=chunk_count,
            duration_ms=elapsed_ms(started_at),
        )
        raise
    finally:
        if not completed:
            trace_log(
                logger,
                logging.WARNING,
                "SSETransport",
                "sse_client_disconnected",
                chunks_sent=chunk_count,
                duration_ms=elapsed_ms(started_at),
            )
