"""Diễn đạt response cuối cùng của chatbot bằng Gemini từ dữ liệu đã kiểm chứng."""

import logging
import os
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from time import perf_counter
from typing import cast

from app.dialog.instruction_builder import DialogResponse, InstructionBuilder
from app.domain.booking_context import BookingContext
from app.infrastructure.context_store import elapsed_ms, record_turn_metrics, trace_log
from app.infrastructure.gemini_client import LLMGateway, LLMGatewayError, LLMMessage

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ResponseGenerationEvent:
    """
    Một event nội bộ của NLG streaming.

    - `delta`: phần text nhỏ để UI render dần.
    - `response`: response cuối cùng vẫn giữ state/status/backend contract.
    """

    delta: str | None = None
    response: DialogResponse | None = None


class ResponseGenerator:
    """
    Lớp NLG của chatbot.

    Nó nhận response draft từ `InstructionBuilder`, dựng prompt grounded cho Gemini
    và chỉ viết lại câu trả lời tự nhiên; nó không được tự đổi business outcome,
    state hay dữ liệu booking.
    """

    # Nhận LLM gateway và InstructionBuilder để diễn đạt response nhưng không đổi business outcome.
    def __init__(self, llm_gateway: LLMGateway, instruction_builder: InstructionBuilder) -> None:
        self._llm_gateway = llm_gateway
        self._instruction_builder = instruction_builder

    # Gửi instruction/context sang LLM NLG và fallback về text cũ nếu provider lỗi.
    async def generate(
        self,
        *,
        response: DialogResponse,
        context: BookingContext,
    ) -> DialogResponse:
        prompt = self._instruction_builder.build_nlg_prompt(
            response=response,
            context=context,
        )
        started = perf_counter()
        _log_nlg_started(prompt=prompt, response=response, event_name="nlg_started")
        try:
            generated = await self._llm_gateway.generate(_nlg_messages(prompt))
            text = generated.content.strip() if generated.content else ""
            if not text:
                raise ValueError("Gemini returned an empty NLG response.")
        except (LLMGatewayError, TimeoutError, ValueError) as error:
            _log_nlg_failed(error=error, started=started, event_name="nlg_failed")
            return response
        _log_nlg_completed(
            text=text,
            started=started,
            event_name="nlg_completed",
            operation="response_generation",
        )
        return _replace_response_text(response, text)

    # Stream NLG cho SSE: gửi delta để UI hiển thị dần, rồi gửi response cuối để giữ state chuẩn.
    async def stream_generate(
        self,
        *,
        response: DialogResponse,
        context: BookingContext,
    ) -> AsyncIterator[ResponseGenerationEvent]:
        prompt = self._instruction_builder.build_nlg_prompt(
            response=response,
            context=context,
        )
        started = perf_counter()
        _log_nlg_started(prompt=prompt, response=response, event_name="nlg_stream_started")
        streamer = getattr(self._llm_gateway, "stream_generate", None)
        if not callable(streamer):
            yield ResponseGenerationEvent(
                response=await self.generate(response=response, context=context)
            )
            return

        text_parts: list[str] = []
        try:
            stream_generate = cast(
                Callable[[list[LLMMessage]], AsyncIterator[str]],
                streamer,
            )
            async for delta in stream_generate(_nlg_messages(prompt)):
                if not delta:
                    continue
                text_parts.append(delta)
                yield ResponseGenerationEvent(delta=delta)
            text = "".join(text_parts).strip()
            if not text:
                raise ValueError("Gemini returned an empty NLG stream.")
        except (LLMGatewayError, TimeoutError, ValueError) as error:
            _log_nlg_failed(error=error, started=started, event_name="nlg_stream_failed")
            yield ResponseGenerationEvent(response=response)
            return
        _log_nlg_completed(
            text=text,
            started=started,
            event_name="nlg_stream_completed",
            operation="response_generation_stream",
        )
        yield ResponseGenerationEvent(response=_replace_response_text(response, text))


def _nlg_messages(prompt: str) -> list[LLMMessage]:
    return [
        LLMMessage(
            role="system",
            content=(
                "Bạn là Kori. Chỉ diễn đạt lại dữ liệu backend đã kiểm chứng; "
                "không sáng tạo dữ liệu booking."
            ),
        ),
        LLMMessage(role="user", content=prompt),
    ]


def _replace_response_text(response: DialogResponse, text: str) -> DialogResponse:
    return DialogResponse(
        text=text,
        instruction_template=response.instruction_template,
        state=response.state,
        status=response.status,
        quick_replies=response.quick_replies,
        metadata=response.metadata,
    )


def _log_nlg_started(
    *,
    prompt: str,
    response: DialogResponse,
    event_name: str,
) -> None:
    if _full_prompt_logging_enabled():
        trace_log(
            logger,
            logging.DEBUG,
            "InstructionBuilder",
            "instruction_prompt",
            prompt=prompt,
        )
    trace_log(
        logger,
        logging.DEBUG,
        "[7] RESPONSE",
        event_name,
        provider="gemini",
        operation="response_generation",
        template_key=response.instruction_template or "none",
        prompt_chars=len(prompt),
    )


def _log_nlg_failed(
    *,
    error: Exception,
    started: float,
    event_name: str,
) -> None:
    record_turn_metrics(nlg_duration_ms=elapsed_ms(started))
    trace_log(
        logger,
        logging.WARNING,
        "ResponseGenerator",
        event_name,
        operation="response_generation",
        error_code=type(error).__name__,
        duration_ms=elapsed_ms(started),
    )


def _log_nlg_completed(
    *,
    text: str,
    started: float,
    event_name: str,
    operation: str,
) -> None:
    trace_log(
        logger,
        logging.DEBUG,
        "[7] RESPONSE",
        event_name,
        operation=operation,
        response_length=len(text),
        duration_ms=elapsed_ms(started),
    )
    record_turn_metrics(nlg_duration_ms=elapsed_ms(started))


# Chỉ cho phép log prompt đầy đủ trong local/debug để tránh lộ dữ liệu nhạy cảm.
def _full_prompt_logging_enabled() -> bool:
    environment = os.getenv("APP_ENV", "production").strip().casefold()
    enabled = os.getenv("LOG_LLM_PROMPTS", "false").strip().casefold()
    return environment in {"local", "development", "dev"} and enabled in {
        "1",
        "true",
        "yes",
        "on",
    }
