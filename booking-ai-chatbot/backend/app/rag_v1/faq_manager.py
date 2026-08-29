from app.dialog.instruction_builder import DialogResponse, InstructionBuilder
from app.domain.booking_context import BookingContext
from app.infrastructure.gemini_client import LLMGatewayError
from app.rag_v1.service import RAGService

_UNAVAILABLE_TEXT = (
    "Hiện tại mình chưa thể tra cứu thông tin này. "
    "Anh/chị vui lòng thử lại sau nhé."
)


# ============================================================
# FAQManager
# ============================================================
#
# Class này là điểm nối giữa chatbot flow và RAG v1.
#
# DialogController không cần biết RAG bên dưới dùng:
#
# - semantic search
# - keyword search BM25
# - RRF
# - reranker
#
# DialogController chỉ gọi:
#
# container.faq_manager.answer(query, context)
#
# FAQManager sẽ gọi RAG pipeline rồi trả về DialogResponse
# đúng contract hiện tại của chatbot.
#
# ============================================================


class FAQManager:

    def __init__(
        self,
        *,
        instruction_builder: InstructionBuilder,
        rag_service: RAGService | None = None,
    ) -> None:
        """
        Khởi tạo FAQManager.

        Runtime production:
            truyền RAGService để mọi câu trả lời FAQ đều đi qua LLM.
        """

        # ----------------------------------------------------
        # 1. Lưu dependencies
        # ----------------------------------------------------
        #
        # instruction_builder:
        #     convert text cuối cùng thành DialogResponse.
        #
        # rag_service:
        #     chạy full RAG pipeline:
        #     Retriever → Reranker → PromptBuilder → Gemini.
        # ----------------------------------------------------

        self._instruction_builder = instruction_builder
        self.instruction_builder = instruction_builder
        self.rag_service = rag_service


    async def answer(
        self,
        *,
        query: str,
        context: BookingContext,
    ) -> DialogResponse:
        """
        Trả lời FAQ bằng RAG nhưng vẫn giữ state chatbot hiện tại.
        """

        # ----------------------------------------------------
        # STEP 1: Validate query
        # ----------------------------------------------------

        if not query.strip():
            raise ValueError(
                "query cannot be empty."
            )


        # ----------------------------------------------------
        # STEP 2: Call RAGService
        # ----------------------------------------------------
        #
        # Đây là điểm quan trọng:
        #
        # FAQManager KHÔNG tự ghép document thành answer.
        #
        # Nó gọi RAGService để câu trả lời đi qua LLM:
        #
        # query
        #   ↓
        # Retriever
        #   ↓
        # Reranker
        #   ↓
        # PromptBuilder
        #   ↓
        # Gemini
        #   ↓
        # answer text
        # ----------------------------------------------------

        if self.rag_service is None:
            return self._build_failure_response(
                text=_UNAVAILABLE_TEXT,
                context=context,
            )

        try:
            answer = await self.rag_service.answer(
                query
            )
        except (LLMGatewayError, TimeoutError, ValueError):
            return self._build_failure_response(
                text=_UNAVAILABLE_TEXT,
                context=context,
            )


        # ----------------------------------------------------
        # STEP 3: Return DialogResponse
        # ----------------------------------------------------
        #
        # DialogResponse là contract mà chat_api/frontend đang dùng.
        #
        # RAGService trả string từ LLM.
        # FAQManager wrap string đó thành DialogResponse.
        # ----------------------------------------------------

        return self.instruction_builder.build_faq_response(
            answer=answer,
            source_count=0,
            context=context,
        )


    def _build_failure_response(
        self,
        *,
        text: str,
        context: BookingContext,
    ) -> DialogResponse:
        """
        Render lỗi FAQ an toàn, không lộ lỗi hạ tầng ra người dùng.
        """

        return self.instruction_builder.build_faq_response(
            answer=text,
            source_count=0,
            context=context,
            handled_failure=True,
        )
