"""Unit tests for FAQManager as the chatbot adapter to RAGService."""

import asyncio
from copy import deepcopy
from typing import cast

import pytest

from app.dialog.dialog_controller import DialogTurnStatus
from app.dialog.instruction_builder import DialogResponse, InstructionBuilder
from app.domain.booking_context import BookingContext
from app.domain.booking_state import BookingState
from app.infrastructure.gemini_client import LLMGatewayError
from app.rag_v1.faq_manager import FAQManager
from app.rag_v1.service import RAGService


class FakeRAGService:
    def __init__(
        self,
        answer_text: str = "LLM grounded answer",
        error: BaseException | None = None,
    ) -> None:
        self.answer_text = answer_text
        self.error = error
        self.calls: list[str] = []

    async def answer(
        self,
        query: str,
    ) -> str:
        self.calls.append(
            query
        )

        if self.error is not None:
            raise self.error

        return self.answer_text


class RecordingInstructionBuilder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int, BookingContext, bool]] = []

    def build_faq_response(
        self,
        *,
        answer: str,
        source_count: int,
        context: BookingContext,
        handled_failure: bool = False,
    ) -> DialogResponse:
        self.calls.append(
            (
                answer,
                source_count,
                context,
                handled_failure,
            )
        )
        return DialogResponse(
            text=answer,
            instruction_template=None,
            state=context.state,
            status=(
                DialogTurnStatus.FAILURE_HANDLED
                if handled_failure
                else DialogTurnStatus.SUCCESS
            ),
            metadata={
                "response_type": "faq",
                "source_count": source_count,
            },
        )


def manager_for(
    rag_service: FakeRAGService | None,
) -> tuple[FAQManager, RecordingInstructionBuilder]:
    builder = RecordingInstructionBuilder()
    return (
        FAQManager(
            rag_service=cast(RAGService | None, rag_service),
            instruction_builder=cast(InstructionBuilder, builder),
        ),
        builder,
    )


@pytest.mark.asyncio
async def test_answer_calls_rag_service_and_wraps_llm_text() -> None:
    rag_service = FakeRAGService(
        "Cửa hàng mở cửa từ 08:00 đến 22:00."
    )
    manager, builder = manager_for(
        rag_service
    )
    context = BookingContext(
        "faq-llm"
    )

    response = await manager.answer(
        query="Giờ mở cửa là mấy giờ?",
        context=context,
    )

    assert response.status is DialogTurnStatus.SUCCESS
    assert response.text == "Cửa hàng mở cửa từ 08:00 đến 22:00."
    assert response.metadata == {
        "response_type": "faq",
        "source_count": 0,
    }
    assert rag_service.calls == [
        "Giờ mở cửa là mấy giờ?",
    ]
    assert builder.calls == [
        (
            response.text,
            0,
            context,
            False,
        )
    ]


@pytest.mark.asyncio
async def test_missing_rag_service_renders_safe_unavailable_response() -> None:
    manager, builder = manager_for(
        None
    )
    context = BookingContext(
        "faq-none"
    )

    response = await manager.answer(
        query="Opening hours?",
        context=context,
    )

    assert response.status is DialogTurnStatus.FAILURE_HANDLED
    assert "tra cứu" in response.text
    assert builder.calls == [
        (
            response.text,
            0,
            context,
            True,
        )
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        LLMGatewayError("provider failed"),
        TimeoutError("timeout"),
        ValueError("empty response"),
    ],
)
async def test_rag_service_known_failures_render_safe_response(
    error: Exception,
) -> None:
    rag_service = FakeRAGService(
        error=error
    )
    manager, builder = manager_for(
        rag_service
    )
    context = BookingContext(
        "faq-failure"
    )

    response = await manager.answer(
        query="Parking?",
        context=context,
    )

    assert response.status is DialogTurnStatus.FAILURE_HANDLED
    assert "provider failed" not in response.text
    assert "timeout" not in response.text
    assert "empty response" not in response.text
    assert rag_service.calls == [
        "Parking?",
    ]
    assert builder.calls == [
        (
            response.text,
            0,
            context,
            True,
        )
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [asyncio.CancelledError(), RuntimeError("bug")])
async def test_cancellation_and_programmer_errors_propagate(
    error: BaseException,
) -> None:
    rag_service = FakeRAGService(
        error=error
    )
    manager, builder = manager_for(
        rag_service
    )

    with pytest.raises(type(error)):
        await manager.answer(
            query="FAQ",
            context=BookingContext("faq-error"),
        )

    assert rag_service.calls == [
        "FAQ",
    ]
    assert builder.calls == []


@pytest.mark.asyncio
async def test_context_is_not_mutated_and_active_state_reminder_is_rendered() -> None:
    rag_service = FakeRAGService(
        "Open until 22:00."
    )
    builder = InstructionBuilder()
    manager = FAQManager(
        rag_service=cast(RAGService, rag_service),
        instruction_builder=builder,
    )
    context = BookingContext(
        "faq-state",
        state=BookingState.SELECTING_TIME,
    )
    before = deepcopy(
        context
    )

    response = await manager.answer(
        query="Closing time?",
        context=context,
    )

    assert "Open until 22:00." in response.text
    assert "khung" in response.text
    assert response.state is BookingState.SELECTING_TIME
    assert context == before
    assert not hasattr(manager, "_context_store")
