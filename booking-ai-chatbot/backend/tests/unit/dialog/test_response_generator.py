"""Tests for grounded Gemini response generation."""

from app.dialog.dialog_controller import DialogTurnStatus
from app.dialog.instruction_builder import DialogResponse, InstructionBuilder
from app.dialog.response_generator import ResponseGenerator
from app.domain.booking_context import BookingContext
from app.domain.booking_state import BookingState
from app.infrastructure.gemini_client import (
    LLMGatewayUnavailableError,
    LLMMessage,
    LLMResponse,
)


class FakeLLM:
    def __init__(
        self,
        response: LLMResponse | None = None,
        error: Exception | None = None,
    ) -> None:
        self.response = response or LLMResponse(content="Bạn muốn chọn ngày nào?")
        self.error = error
        self.messages: list[LLMMessage] = []

    async def generate(
        self,
        messages: list[LLMMessage],
        *,
        tools: list[dict[str, object]] | None = None,
    ) -> LLMResponse:
        self.messages = messages
        if self.error is not None:
            raise self.error
        return self.response


def response() -> DialogResponse:
    return DialogResponse(
        "Bạn muốn đặt lịch vào ngày nào?",
        "ask_date",
        BookingState.SELECTING_DATE,
        DialogTurnStatus.SUCCESS,
        ("Hôm nay", "Ngày mai"),
    )


async def test_generator_replaces_only_text_and_preserves_backend_contract() -> None:
    gateway = FakeLLM()
    generator = ResponseGenerator(gateway, InstructionBuilder())

    generated = await generator.generate(
        response=response(),
        context=BookingContext("conversation-1", state=BookingState.SELECTING_DATE),
    )

    assert generated.text == "Bạn muốn chọn ngày nào?"
    assert generated.state is BookingState.SELECTING_DATE
    assert generated.quick_replies == ("Hôm nay", "Ngày mai")
    assert "Không thêm shop" in gateway.messages[1].content


async def test_generator_uses_safe_fallback_on_provider_failure_or_empty_text() -> None:
    context = BookingContext("conversation-1", state=BookingState.SELECTING_DATE)
    unavailable = ResponseGenerator(
        FakeLLM(error=LLMGatewayUnavailableError("offline")),
        InstructionBuilder(),
    )
    empty = ResponseGenerator(FakeLLM(LLMResponse(content="  ")), InstructionBuilder())

    assert await unavailable.generate(response=response(), context=context) == response()
    assert await empty.generate(response=response(), context=context) == response()
