"""
Mã hóa và stream các event SSE dạng JSON cho response hội thoại.
"""

import asyncio
import inspect
import json
import logging
import re
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from enum import StrEnum
from time import perf_counter
from typing import TYPE_CHECKING

from app.infrastructure.context_store import (
    bind_trace_context,
    consume_completed_turn_metrics,
    elapsed_ms,
    reset_trace_context,
    trace_log,
    turn_metrics_payload,
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
    """
    Các event tầng nghiệp vụ mà endpoint SSE của chatbot phát ra.
    """

    STARTED = "started"
    MESSAGE = "message"
    COMPLETED = "completed"
    ERROR = "error"


class InvalidSSEEventError(ValueError):
    """
    Phát sinh khi tên event hoặc payload SSE không hợp lệ.
    """
    pass


class SSESerializationError(TypeError):
    """
    Phát sinh khi payload SSE không thể serialize thành JSON.
    """
    pass


# Mã hóa một event SSE thành đúng định dạng text/event-stream gửi về frontend.
def encode_sse_event(
    *,
    event: str,
    data: Mapping[str, object],
) -> str:
    # Tạo một frame SSE gọn, chứa đúng một object JSON hợp lệ.
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


# Stream started/message/completed để frontend biết vòng đời của một lượt chat.
async def stream_chat_events(
    *,
    request: "ChatRequest",
    container: "ApplicationContainer",
    process_message: ProcessMessage,
    response_mapper: ResponseMapper,
    correlation_id: str | None = None,
    entrypoint: str | None = None,
) -> AsyncIterator[str]:
    # Phát đầy đủ vòng đời SSE cho một lần gọi `process_message`.
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
            entrypoint=entrypoint,
        ):
            yield event
    finally:
        try:
            reset_trace_context(token)
        except ValueError:
            logger.debug("trace_context_reset_skipped", exc_info=True)


# Bao lỗi trong quá trình stream thành event error an toàn thay vì làm đứt kết nối thô.
async def _stream_bound_chat_events(
    *,
    request: "ChatRequest",
    container: "ApplicationContainer",
    process_message: ProcessMessage,
    response_mapper: ResponseMapper,
    correlation_id: str | None,
    entrypoint: str | None,
) -> AsyncIterator[str]:
    # Chạy một turn nghiệp vụ rồi phát tuần tự các event started/message/completed.
    started_at = perf_counter()
    chunk_count = 0
    bytes_sent = 0
    completed = False
    trace_log(logger, logging.DEBUG, "SSETransport", "sse_started")
    started_event = encode_sse_event(
        event=SSEEventType.STARTED,
        data={"conversation_id": request.conversation_id},
    )
    chunk_count += 1
    bytes_sent += len(started_event.encode("utf-8"))
    yield started_event

    try:
        dialog_response = await _call_process_message(
            process_message=process_message,
            request=request,
            container=container,
            correlation_id=correlation_id,
            entrypoint=entrypoint,
        )
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
            "sse_failed",
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
        metrics = consume_completed_turn_metrics()
        trace_log(
            logger,
            logging.INFO,
            "[9] DELIVERY",
            "completed",
            channel="sse",
            duration_ms=elapsed_ms(started_at),
            client_disconnected=False,
        )
        if metrics is not None:
            trace_log(
                logger,
                logging.INFO,
                "[10] TURN METRICS",
                "completed",
                metrics=turn_metrics_payload(metrics, total_duration_ms=elapsed_ms(started_at)),
            )
        trace_log(
            logger,
            logging.DEBUG,
            "SSETransport",
            "sse_stream_stats",
            chunk_count=chunk_count,
            bytes_sent=bytes_sent,
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


# Chỉ truyền các tham số mà process_message thực sự khai báo để giữ tương thích với test double cũ.
async def _call_process_message(
    *,
    process_message: ProcessMessage,
    request: "ChatRequest",
    container: "ApplicationContainer",
    correlation_id: str | None,
    entrypoint: str | None,
) -> "DialogResponse":
    parameters = inspect.signature(process_message).parameters
    kwargs: dict[str, object] = {"request": request, "container": container}
    if correlation_id is not None and "correlation_id" in parameters:
        kwargs["correlation_id"] = correlation_id
    if entrypoint is not None and "entrypoint" in parameters:
        kwargs["entrypoint"] = entrypoint
    return await process_message(**kwargs)
