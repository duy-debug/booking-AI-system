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
        self.response = response or LLMResponse(content="Anh/chị muốn chọn ngày nào?")
        self.error = error
        self.messages: list[LLMMessage] = []
        self.call_count = 0

    async def generate(
        self,
        messages: list[LLMMessage],
        *,
        tools: list[dict[str, object]] | None = None,
    ) -> LLMResponse:
        self.call_count += 1
        self.messages = messages
        if self.error is not None:
            raise self.error
        return self.response


class FakeStreamingLLM(FakeLLM):
    def __init__(self, chunks: tuple[str, ...]) -> None:
        super().__init__()
        self.chunks = chunks

    async def stream_generate(
        self,
        messages: list[LLMMessage],
        *,
        tools: list[dict[str, object]] | None = None,
    ):
        self.call_count += 1
        self.messages = messages
        for chunk in self.chunks:
            yield chunk


def response() -> DialogResponse:
    return DialogResponse(
        (
            "Anh/chị muốn đặt lịch vào ngày nào? "
            "Anh/chị có thể nhập hôm nay, ngày mai hoặc một ngày cụ thể "
            "để mình kiểm tra lịch trống phù hợp."
        ),
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

    assert generated.text == "Anh/chị muốn chọn ngày nào?"
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


async def test_stream_generator_yields_deltas_then_final_response() -> None:
    gateway = FakeStreamingLLM(("Xin", " chào"))
    generator = ResponseGenerator(gateway, InstructionBuilder())

    events = [
        event
        async for event in generator.stream_generate(
            response=response(),
            context=BookingContext("conversation-1", state=BookingState.SELECTING_DATE),
        )
    ]

    assert [event.delta for event in events] == ["Xin", " chào", None]
    assert events[-1].response is not None
    assert events[-1].response.text == "Xin chào"
    assert events[-1].response.state is BookingState.SELECTING_DATE


def structured_response() -> DialogResponse:
    return DialogResponse(
        (
            "Please confirm booking:\n"
            "Customer name: Duy\n"
            "Phone: 0773582649\n"
            "Shop: Komorebi Binh Thanh\n"
            "Date: 29/08/2026\n"
            "Time: 14:00\n"
            "People: 2\n"
            "Duration: 75 minutes\n"
            "Course: Massage giu am\n"
            "Add-on: Ngam chan gung\n"
            "Therapist: No preference\n"
            "\n"
            "Do you want to confirm this booking?"
        ),
        "final_confirmation",
        BookingState.AWAITING_CONFIRMATION,
        DialogTurnStatus.SUCCESS,
        ("Xac nhan", "Chinh sua", "Huy"),
        metadata={"preserve_structured_text": True},
    )


async def test_structured_response_keeps_valid_nlg_intro_and_original_form() -> None:
    original = structured_response()
    rewritten = f"Da, em gui lai thong tin lich hen:\n{original.text}"
    gateway = FakeLLM(LLMResponse(content=rewritten))
    generator = ResponseGenerator(gateway, InstructionBuilder())

    generated = await generator.generate(
        response=original,
        context=BookingContext("conversation-1", state=BookingState.AWAITING_CONFIRMATION),
    )

    assert generated.text == rewritten
    assert gateway.call_count == 1


async def test_structured_response_falls_back_when_nlg_flattens_form_lines() -> None:
    original = structured_response()
    gateway = FakeLLM(
        LLMResponse(
            content=original.text.replace("\n", " ")
        )
    )
    generator = ResponseGenerator(gateway, InstructionBuilder())

    generated = await generator.generate(
        response=original,
        context=BookingContext("conversation-1", state=BookingState.AWAITING_CONFIRMATION),
    )

    assert generated.text == original.text
    assert gateway.call_count == 1


async def test_structured_response_falls_back_when_nlg_drops_form_lines() -> None:
    original = structured_response()
    gateway = FakeLLM(
        LLMResponse(
            content=(
                "Da, Komorebi Binh Thanh da ghi nhan lich hen "
                "14:00 ngay 29/08/2026. Anh/chi xac nhan giup em nhe?"
            )
        )
    )
    generator = ResponseGenerator(gateway, InstructionBuilder())

    generated = await generator.generate(
        response=original,
        context=BookingContext("conversation-1", state=BookingState.AWAITING_CONFIRMATION),
    )

    assert generated.text == original.text
    assert gateway.call_count == 1


async def test_structured_stream_buffers_deltas_and_falls_back_when_form_is_dropped() -> None:
    original = structured_response()
    gateway = FakeStreamingLLM(("Da, ", "em da ghi nhan lich hen."))
    generator = ResponseGenerator(gateway, InstructionBuilder())

    events = [
        event
        async for event in generator.stream_generate(
            response=original,
            context=BookingContext("conversation-1", state=BookingState.AWAITING_CONFIRMATION),
        )
    ]

    assert [event.delta for event in events] == [None]
    assert events[-1].response is not None
    assert events[-1].response.text == original.text
    assert gateway.call_count == 1
