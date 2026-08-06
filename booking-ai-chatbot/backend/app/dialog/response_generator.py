"""Generate the final grounded assistant text through Gemini."""

import logging
import os
from time import perf_counter

from app.dialog.instruction_builder import DialogResponse, InstructionBuilder
from app.domain.booking_context import BookingContext
from app.infrastructure.context_store import elapsed_ms, record_turn_metrics, trace_log
from app.infrastructure.gemini_client import LLMGateway, LLMGatewayError, LLMMessage

logger = logging.getLogger(__name__)


class ResponseGenerator:
    """Use Gemini for NLG while preserving backend-owned response metadata."""

    def __init__(self, llm_gateway: LLMGateway, instruction_builder: InstructionBuilder) -> None:
        self._llm_gateway = llm_gateway
        self._instruction_builder = instruction_builder

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
            logging.INFO,
            "ResponseGenerator",
            "nlg_started",
            provider="gemini",
            operation="response_generation",
            template_key=response.instruction_template or "none",
            prompt_chars=len(prompt),
        )
        try:
            generated = await self._llm_gateway.generate(
                [
                    LLMMessage(
                        role="system",
                        content=(
                            "Bạn là Kori. Chỉ diễn đạt lại dữ liệu backend đã kiểm chứng; "
                            "không sáng tạo dữ liệu booking."
                        ),
                    ),
                    LLMMessage(role="user", content=prompt),
                ]
            )
            text = generated.content.strip() if generated.content else ""
            if not text:
                raise ValueError("Gemini returned an empty NLG response.")
        except (LLMGatewayError, TimeoutError, ValueError) as error:
            record_turn_metrics(nlg_duration_ms=elapsed_ms(started))
            trace_log(
                logger,
                logging.WARNING,
                "ResponseGenerator",
                "nlg_failed",
                operation="response_generation",
                error_code=type(error).__name__,
                duration_ms=elapsed_ms(started),
            )
            return response
        trace_log(
            logger,
            logging.INFO,
            "ResponseGenerator",
            "nlg_completed",
            operation="response_generation",
            response_length=len(text),
            duration_ms=elapsed_ms(started),
        )
        record_turn_metrics(nlg_duration_ms=elapsed_ms(started))
        return DialogResponse(
            text=text,
            instruction_template=response.instruction_template,
            state=response.state,
            status=response.status,
            quick_replies=response.quick_replies,
            metadata=response.metadata,
        )


def _full_prompt_logging_enabled() -> bool:
    environment = os.getenv("APP_ENV", "production").strip().casefold()
    enabled = os.getenv("LOG_LLM_PROMPTS", "false").strip().casefold()
    return environment in {"local", "development", "dev"} and enabled in {
        "1",
        "true",
        "yes",
        "on",
    }
