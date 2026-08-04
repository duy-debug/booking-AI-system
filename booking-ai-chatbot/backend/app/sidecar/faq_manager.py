"""Coordinate deterministic FAQ retrieval outside the booking state machine."""

import logging
from time import perf_counter

from app.application.ports.knowledge_gateway import (
    KnowledgeDocument,
    KnowledgeGateway,
    KnowledgeGatewayError,
)
from app.core.logging import elapsed_ms, trace_log
from app.dialog.instruction_builder import DialogResponse, InstructionBuilder
from app.domain.booking_context import BookingContext

_FAQ_UNAVAILABLE_TEXT = (
    "Hiện tại hệ thống chưa thể tra cứu thông tin này. "
    "Vui lòng liên hệ cửa hàng để được hỗ trợ."
)
_FAQ_NO_RESULT_TEXT = (
    "Hiện tại tôi chưa có đủ thông tin để trả lời câu hỏi này. "
    "Bạn có thể liên hệ cửa hàng để được hỗ trợ."
)
_MAX_DOCUMENTS = 3
_MAX_ANSWER_CHARS = 2_000
_LOGGER = logging.getLogger(__name__)


class FAQManager:
    """Own the FAQ retrieval policy without mutating booking context."""

    def __init__(
        self,
        *,
        knowledge_gateway: KnowledgeGateway | None,
        instruction_builder: InstructionBuilder,
        min_relevance_score: float = 0.45,
    ) -> None:
        if (
            isinstance(min_relevance_score, bool)
            or not isinstance(min_relevance_score, int | float)
            or not 0.0 <= min_relevance_score <= 1.0
        ):
            raise ValueError("FAQ relevance threshold must be between zero and one.")
        self._knowledge_gateway = knowledge_gateway
        self._instruction_builder = instruction_builder
        self._min_relevance_score = float(min_relevance_score)

    async def answer(
        self,
        *,
        query: str,
        context: BookingContext,
    ) -> DialogResponse:
        """Retrieve and render one FAQ answer while preserving booking state."""
        started_at = perf_counter()
        gateway = self._knowledge_gateway
        if gateway is None:
            self._log_failure("qdrant_disabled", started_at)
            return self._render_unavailable(context)
        try:
            documents = await gateway.search(query, limit=_MAX_DOCUMENTS)
        except KnowledgeGatewayError:
            self._log_failure("knowledge_gateway_unavailable", started_at)
            return self._render_unavailable(context)
        accepted = [
            document
            for document in documents
            if document.score >= self._min_relevance_score
        ]
        top_score = max((document.score for document in documents), default=None)
        contents = _document_contents(accepted)
        if not contents:
            trace_log(
                _LOGGER,
                logging.INFO,
                "Knowledge",
                "no_result",
                operation="faq_retrieval",
                candidate_count=len(documents),
                accepted_result_count=0,
                top_score=top_score,
                error_code="no_relevant_result",
                duration_ms=elapsed_ms(started_at),
            )
            return self._instruction_builder.build_faq_response(
                answer=_FAQ_NO_RESULT_TEXT,
                source_count=0,
                context=context,
                handled_failure=True,
            )
        trace_log(
            _LOGGER,
            logging.INFO,
            "Knowledge",
            "completed",
            operation="faq_retrieval",
            candidate_count=len(documents),
            accepted_result_count=len(contents),
            top_score=top_score,
            duration_ms=elapsed_ms(started_at),
        )
        return self._instruction_builder.build_faq_response(
            answer="\n\n".join(contents),
            source_count=len(contents),
            context=context,
        )

    @staticmethod
    def _log_failure(error_code: str, started_at: float) -> None:
        trace_log(
            _LOGGER,
            logging.WARNING,
            "Knowledge",
            "failed",
            operation="faq_retrieval",
            error_code=error_code,
            duration_ms=elapsed_ms(started_at),
        )

    def _render_unavailable(self, context: BookingContext) -> DialogResponse:
        return self._instruction_builder.build_faq_response(
            answer=_FAQ_UNAVAILABLE_TEXT,
            source_count=0,
            context=context,
            handled_failure=True,
        )


def _document_contents(
    documents: list[KnowledgeDocument],
) -> tuple[str, ...]:
    contents: list[str] = []
    seen: set[str] = set()
    current_length = 0
    for document in documents[:_MAX_DOCUMENTS]:
        if not isinstance(document, KnowledgeDocument) or not isinstance(
            document.content, str
        ):
            continue
        content = " ".join(document.content.split())
        deduplication_key = content.casefold()
        if not content or deduplication_key in seen:
            continue
        separator_length = 2 if contents else 0
        remaining = _MAX_ANSWER_CHARS - current_length - separator_length
        if remaining <= 0:
            break
        normalized = content[:remaining].rstrip()
        if not normalized:
            break
        contents.append(normalized)
        seen.add(deduplication_key)
        current_length += separator_length + len(normalized)
    return tuple(contents)
