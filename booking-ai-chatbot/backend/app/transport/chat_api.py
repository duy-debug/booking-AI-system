"""Expose JSON and streaming HTTP transports for dialog messages."""

from __future__ import annotations

import inspect
import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from time import perf_counter
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from app.dependencies import (
    ApplicationContainer,
    InvalidCachedContextError,
    InvalidConversationContextError,
    InvalidConversationIdError,
)
from app.dialog.instruction_builder import DialogResponse
from app.infrastructure.context_store import (
    consume_completed_turn_metrics,
    elapsed_ms,
    trace_log,
    turn_metrics_payload,
)
from app.transport.schemas import ChatRequest, ChatResponse
from app.transport.sse import stream_chat_events

router = APIRouter(prefix="/api/v1")

_SAFE_METADATA_KEYS = frozenset(
    {
        "available_slot_count",
        "has_addons",
        "booking_created",
        "can_retry",
        "can_change_info",
        "response_type",
        "source_count",
        "item_count",
    }
)


# Lấy ApplicationContainer đã được khởi tạo trong lifespan để transport không tự tạo dependency.
def get_application_container(request: Request) -> ApplicationContainer:
    """Return the single container created by the FastAPI lifespan."""
    container = getattr(request.app.state, "application_container", None)
    if not isinstance(container, ApplicationContainer):
        raise RuntimeError("Application container is unavailable.")
    return container


@router.post("/chat", response_model=ChatResponse)
# Nhận request JSON và chuyển toàn bộ xử lý nghiệp vụ xuống DialogController.
async def chat(
    request: ChatRequest,
    http_request: Request,
    container: Annotated[ApplicationContainer, Depends(get_application_container)],
) -> ChatResponse:
    """Process one non-streaming chat message."""
    started_at = perf_counter()
    try:
        response = await _process_chat_message(
            request=request,
            container=container,
            correlation_id=http_request.headers.get("x-correlation-id"),
            entrypoint="/api/v1/chat",
        )
    except InvalidConversationIdError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Invalid conversation ID.",
        ) from error
    except (InvalidCachedContextError, InvalidConversationContextError) as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error.",
        ) from error
    metrics = consume_completed_turn_metrics()
    trace_log(
        logging.getLogger(__name__),
        logging.INFO,
        "[9] DELIVERY",
        "completed",
        channel="json",
        status="completed",
        duration_ms=elapsed_ms(started_at),
    )
    if metrics is not None:
        trace_log(
            logging.getLogger(__name__),
            logging.INFO,
            "[10] TURN METRICS",
            "completed",
            metrics=turn_metrics_payload(metrics, total_duration_ms=elapsed_ms(started_at)),
        )
    return _to_chat_response(request.conversation_id, response)


@router.post("/chat/stream", response_class=StreamingResponse)
# Nhận request SSE và stream kết quả theo cùng pipeline xử lý với JSON endpoint.
async def chat_stream(
    request: ChatRequest,
    http_request: Request,
    container: Annotated[ApplicationContainer, Depends(get_application_container)],
) -> StreamingResponse:
    """Stream one dialog response as business-level SSE events."""
    return StreamingResponse(
        _stream_chat_events(
            request=request,
            container=container,
            correlation_id=http_request.headers.get("x-correlation-id"),
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# Chạy một lượt chat qua DialogController và map lỗi runtime thành response an toàn.
async def _process_chat_message(
    *,
    request: ChatRequest,
    container: ApplicationContainer,
    correlation_id: str | None = None,
    entrypoint: str | None = None,
) -> DialogResponse:
    """Delegate one complete business turn to DialogController."""
    parameters = inspect.signature(container.dialog_controller.handle_message).parameters
    if "entrypoint" in parameters:
        return await container.dialog_controller.handle_message(
            conversation_id=request.conversation_id,
            message=request.message,
            idempotency_key=request.idempotency_key,
            correlation_id=correlation_id,
            entrypoint=entrypoint,
        )
    return await container.dialog_controller.handle_message(
        conversation_id=request.conversation_id,
        message=request.message,
        idempotency_key=request.idempotency_key,
        correlation_id=correlation_id,
    )


# Tạo generator SSE từ cùng kết quả xử lý business turn của DialogController.
def _stream_chat_events(
    *,
    request: ChatRequest,
    container: ApplicationContainer,
    correlation_id: str | None = None,
) -> AsyncIterator[str]:
    """Delegate SSE lifecycle generation to the SSE transport module."""
    async def process_stream_message(
        *,
        request: ChatRequest,
        container: ApplicationContainer,
        correlation_id: str | None = None,
    ) -> DialogResponse:
        parameters = inspect.signature(_process_chat_message).parameters
        kwargs: dict[str, object] = {
            "request": request,
            "container": container,
        }
        if correlation_id is not None and "correlation_id" in parameters:
            kwargs["correlation_id"] = correlation_id
        if "entrypoint" in parameters:
            kwargs["entrypoint"] = "/api/v1/chat/stream"
        process_message = cast(Callable[..., Awaitable[DialogResponse]], _process_chat_message)
        return await process_message(**kwargs)

    return stream_chat_events(
        request=request,
        container=container,
        process_message=process_stream_message,
        response_mapper=_to_chat_response,
        correlation_id=correlation_id,
    )


# Chuyển DialogResponse nội bộ thành schema public trả về frontend.
def _to_chat_response(conversation_id: str, response: DialogResponse) -> ChatResponse:
    return ChatResponse(
        conversation_id=conversation_id,
        text=response.text,
        state=response.state.value,
        status=response.status.value,
        instruction_template=response.instruction_template,
        quick_replies=list(response.quick_replies),
        metadata=_safe_metadata(response.metadata),
    )


# Lọc metadata chỉ giữ các kiểu dữ liệu an toàn cho public API.
def _safe_metadata(
    metadata: Mapping[str, object],
) -> dict[str, bool | int | float | str | None]:
    safe: dict[str, bool | int | float | str | None] = {}
    for key, value in metadata.items():
        if key in _SAFE_METADATA_KEYS and (value is None or type(value) in {bool, int, float, str}):
            safe[key] = cast(bool | int | float | str | None, value)
    return safe
