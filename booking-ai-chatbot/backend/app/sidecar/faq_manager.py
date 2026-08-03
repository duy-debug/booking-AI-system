"""Coordinate deterministic FAQ retrieval outside the booking state machine."""

from app.application.ports.knowledge_gateway import (
    KnowledgeDocument,
    KnowledgeGateway,
    KnowledgeGatewayError,
)
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


class FAQManager:
    """Own the FAQ retrieval policy without mutating booking context."""

    def __init__(
        self,
        *,
        knowledge_gateway: KnowledgeGateway | None,
        instruction_builder: InstructionBuilder,
    ) -> None:
        self._knowledge_gateway = knowledge_gateway
        self._instruction_builder = instruction_builder

    async def answer(
        self,
        *,
        query: str,
        context: BookingContext,
    ) -> DialogResponse:
        """Retrieve and render one FAQ answer while preserving booking state."""
        gateway = self._knowledge_gateway
        if gateway is None:
            return self._render_unavailable(context)
        try:
            documents = await gateway.search(query, limit=_MAX_DOCUMENTS)
        except KnowledgeGatewayError:
            return self._render_unavailable(context)
        contents = _document_contents(documents)
        if not contents:
            return self._instruction_builder.build_faq_response(
                answer=_FAQ_NO_RESULT_TEXT,
                source_count=0,
                context=context,
                handled_failure=True,
            )
        return self._instruction_builder.build_faq_response(
            answer="\n\n".join(contents),
            source_count=len(contents),
            context=context,
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
