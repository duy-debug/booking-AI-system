from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import AsyncIterator
from contextlib import suppress
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from redis.exceptions import RedisError

from app.api.schemas import ChatRequest, ChatResponse
from app.application.orchestrator import ConversationOrchestrator, build_orchestrator
from app.core.config import settings
from app.core.exceptions import AppError
from app.core.token_stream import reset_token_emitter, set_token_emitter

router = APIRouter(prefix="/api/v1", tags=["chat"])
legacy_router = APIRouter(prefix="/api", tags=["chat"])
logger = logging.getLogger(__name__)


# Khởi tạo orchestrator tại API composition root, không đưa Depends vào application.
def get_orchestrator() -> ConversationOrchestrator:
    return build_orchestrator()


# Nhận câu hỏi, điều phối qua application service và trả response có schema ổn định.
@router.post("/chat", response_model=ChatResponse)
@legacy_router.post(
    "/chat",
    response_model=ChatResponse,
    include_in_schema=False,
    deprecated=True,
)
async def chat(
    body: ChatRequest,
    orchestrator: Annotated[
        ConversationOrchestrator,
        Depends(get_orchestrator),
    ],
) -> ChatResponse:
    selection = body.selection.model_dump() if body.selection else None
    result = await orchestrator.handle(
        query=body.query,
        conversation_id=body.conversation_id,
        selection=selection,
    )
    return ChatResponse.model_validate(result)


def _sse(event: str, data: Any) -> str:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {payload}\n\n"


def _answer_chunks(answer: str) -> list[str]:
    # Giữ nguyên khoảng trắng để ghép các delta cho kết quả giống hệt answer.
    return re.findall(r"\S+\s*|\s+", answer)


def _problem(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, AppError):
        return exc.detail
    if isinstance(exc, RedisError):
        return {
            "type": "about:blank",
            "title": "Conversation Store Unavailable",
            "status": 503,
            "detail": "Kho trạng thái hội thoại đang tạm thời không khả dụng.",
            "code": "CONVERSATION_STORE_UNAVAILABLE",
        }
    logger.exception("Unhandled SSE chat error", exc_info=exc)
    return {
        "type": "about:blank",
        "title": "Internal Server Error",
        "status": 500,
        "detail": "Hệ thống gặp lỗi không mong đợi.",
        "code": "INTERNAL_ERROR",
    }


async def _stream_chat(
    request: Request,
    body: ChatRequest,
    orchestrator: ConversationOrchestrator,
) -> AsyncIterator[str]:
    yield _sse(
        "start",
        {
            "contract_version": "1.0",
            "conversation_id": body.conversation_id,
        },
    )
    try:
        selection = body.selection.model_dump() if body.selection else None
        loop = asyncio.get_running_loop()
        token_queue: asyncio.Queue[str] = asyncio.Queue()

        def emit_token(delta: str) -> None:
            loop.call_soon_threadsafe(token_queue.put_nowait, delta)

        context_token = set_token_emitter(emit_token)
        try:
            result_task = asyncio.create_task(
                orchestrator.handle(
                    query=body.query,
                    conversation_id=body.conversation_id,
                    selection=selection,
                )
            )
        finally:
            reset_token_emitter(context_token)

        streamed_from_provider = False
        while not result_task.done() or not token_queue.empty():
            if await request.is_disconnected():
                result_task.cancel()
                with suppress(asyncio.CancelledError):
                    await result_task
                return
            try:
                delta = await asyncio.wait_for(token_queue.get(), timeout=0.25)
            except TimeoutError:
                continue
            streamed_from_provider = True
            yield _sse("token", {"delta": delta})

        result = await result_task
        response = ChatResponse.model_validate(result)
        if not streamed_from_provider:
            for delta in _answer_chunks(response.answer):
                if await request.is_disconnected():
                    return
                yield _sse("token", {"delta": delta})
                if settings.SSE_TOKEN_DELAY_MS:
                    await asyncio.sleep(settings.SSE_TOKEN_DELAY_MS / 1000)
        if response.ui is not None:
            yield _sse("ui", {"ui": response.ui.model_dump(mode="json")})
        yield _sse("done", response.model_dump(mode="json"))
    except Exception as exc:
        yield _sse("error", _problem(exc))


@router.post(
    "/chat/stream",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "SSE stream with start, token, ui, done or error events.",
            "content": {"text/event-stream": {}},
        }
    },
)
async def chat_stream(
    request: Request,
    body: ChatRequest,
    orchestrator: Annotated[
        ConversationOrchestrator,
        Depends(get_orchestrator),
    ],
) -> StreamingResponse:
    return StreamingResponse(
        _stream_chat(request, body, orchestrator),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
