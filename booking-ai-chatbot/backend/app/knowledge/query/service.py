"""Luồng query RAG runtime và orchestration FAQ cho application."""

import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass
from time import perf_counter

from app.dialog.instruction_builder import DialogResponse, InstructionBuilder
from app.domain.booking_context import BookingContext
from app.infrastructure.context_store import elapsed_ms, trace_log
from app.knowledge import KnowledgeDocument, KnowledgeGateway, KnowledgeGatewayError

_FAQ_UNAVAILABLE_TEXT = (
    "Hiện tại hệ thống chưa thể tra cứu thông tin này. "
    "Vui lòng liên hệ cửa hàng để được hỗ trợ."
)
_FAQ_NO_RESULT_TEXT = (
    "Hiện tại tôi chưa có đủ thông tin để trả lời câu hỏi này. "
    "Bạn có thể liên hệ cửa hàng để được hỗ trợ."
)
_LOGGER = logging.getLogger(__name__)
_TOKEN_PATTERN = re.compile(r"\w+", re.UNICODE)


@dataclass(frozen=True, slots=True)
class KnowledgeAnswer:
    """Kết quả đã chuẩn hóa của một lượt query RAG runtime."""

    answer: str | None
    candidate_count: int
    source_count: int
    top_score: float | None


class KnowledgeReranker:
    """Rerank document bằng lexical overlap rồi tới semantic score."""

    def __init__(self, *, top_n: int = 3) -> None:
        if type(top_n) is not int or top_n <= 0:
            raise ValueError("Knowledge rerank top_n must be a positive integer.")
        self._top_n = top_n

    def rerank(
        self,
        *,
        query: str,
        documents: Iterable[KnowledgeDocument],
    ) -> list[KnowledgeDocument]:
        """Trả về các document ưu tiên cao nhất cho một query."""
        # ----------------------------------------------------
        # STEP 1: Kiểm tra query và snapshot document
        # ----------------------------------------------------
        #
        # Reranker không tự gọi Qdrant. Nó chỉ nhận candidate từ retriever
        # và sắp xếp lại trong memory.
        # ----------------------------------------------------
        if not isinstance(query, str) or not query.strip():
            raise ValueError("Knowledge rerank query must not be empty.")
        ranked_documents = list(documents)
        if not ranked_documents:
            return []

        # ----------------------------------------------------
        # STEP 2: Tokenize câu hỏi
        # ----------------------------------------------------
        #
        # Token của query dùng để tính lexical overlap với từng document.
        # Nếu query không tách được token, giữ nguyên thứ tự retriever.
        # ----------------------------------------------------
        query_terms = _tokenize(query)
        if not query_terms:
            return ranked_documents[: self._top_n]

        # ----------------------------------------------------
        # STEP 3: Chấm điểm và sort lại candidate
        # ----------------------------------------------------
        #
        # Sort theo combined score; nếu bằng điểm thì document đứng trước
        # trong kết quả retriever vẫn được ưu tiên hơn.
        # ----------------------------------------------------
        scored = [
            (_combined_score(query_terms, document), index, document)
            for index, document in enumerate(ranked_documents)
        ]
        scored.sort(key=lambda item: (item[0], -item[1]), reverse=True)
        return [document for _, _, document in scored[: self._top_n]]


class KnowledgeSynthesizer:
    """Biến document đã chọn thành một câu trả lời extractive ngắn gọn."""

    def __init__(
        self,
        *,
        max_documents: int = 3,
        max_answer_chars: int = 2_000,
    ) -> None:
        if type(max_documents) is not int or max_documents <= 0:
            raise ValueError("Maximum document count must be a positive integer.")
        if type(max_answer_chars) is not int or max_answer_chars <= 0:
            raise ValueError("Maximum answer length must be a positive integer.")
        self._max_documents = max_documents
        self._max_answer_chars = max_answer_chars

    def synthesize(self, documents: list[KnowledgeDocument]) -> KnowledgeAnswer:
        """Tổng hợp một câu trả lời extractive từ các document đã được chọn."""
        # ----------------------------------------------------
        # STEP 1: Chuẩn bị bộ nhớ deduplicate
        # ----------------------------------------------------
        #
        # Synthesizer hiện không gọi LLM. Nó ghép các đoạn có căn cứ tốt
        # nhất và loại bỏ nội dung trùng nhau.
        # ----------------------------------------------------
        contents: list[str] = []
        seen: set[str] = set()
        current_length = 0

        # ----------------------------------------------------
        # STEP 2: Lấy tối đa max_documents document
        # ----------------------------------------------------
        #
        # Document được normalize whitespace trước khi đưa vào answer để
        # response không bị vỡ bởi xuống dòng/khoảng trắng từ Markdown gốc.
        # ----------------------------------------------------
        for document in documents[: self._max_documents]:
            content = " ".join(document.content.split())
            deduplication_key = content.casefold()
            if not content or deduplication_key in seen:
                continue
            separator_length = 2 if contents else 0
            remaining = self._max_answer_chars - current_length - separator_length
            if remaining <= 0:
                break
            normalized = content[:remaining].rstrip()
            if not normalized:
                break
            contents.append(normalized)
            seen.add(deduplication_key)
            current_length += separator_length + len(normalized)

        # ----------------------------------------------------
        # STEP 3: Trả answer kèm metadata an toàn
        # ----------------------------------------------------
        #
        # Metadata chỉ gồm số candidate, số source dùng thật và top score;
        # không expose vector hoặc payload nội bộ.
        # ----------------------------------------------------
        return KnowledgeAnswer(
            answer="\n\n".join(contents) if contents else None,
            candidate_count=len(documents),
            source_count=len(contents),
            top_score=max((document.score for document in documents), default=None),
        )


class KnowledgeQueryService:
    """Chạy flow RAG runtime: retrieve, filter, rerank và synthesize."""

    def __init__(
        self,
        *,
        knowledge_gateway: KnowledgeGateway,
        min_relevance_score: float = 0.45,
        retrieve_limit: int = 6,
        reranker: KnowledgeReranker | None = None,
        synthesizer: KnowledgeSynthesizer | None = None,
    ) -> None:
        if (
            isinstance(min_relevance_score, bool)
            or not isinstance(min_relevance_score, int | float)
            or not 0.0 <= min_relevance_score <= 1.0
        ):
            raise ValueError("Knowledge relevance threshold must be between zero and one.")
        if type(retrieve_limit) is not int or retrieve_limit <= 0:
            raise ValueError("Knowledge retrieve limit must be a positive integer.")
        self._knowledge_gateway = knowledge_gateway
        self._min_relevance_score = float(min_relevance_score)
        self._retrieve_limit = retrieve_limit
        self._reranker = reranker or KnowledgeReranker(top_n=3)
        self._synthesizer = synthesizer or KnowledgeSynthesizer()

    async def answer(self, query: str) -> KnowledgeAnswer:
        """
        Chạy pipeline query RAG runtime.

        Luồng:

        query
          -> retrieve candidate document
          -> lọc theo relevance score
          -> rerank
          -> synthesize answer
        """

        # ----------------------------------------------------
        # STEP 1: Retrieve các tài liệu ứng viên
        # ----------------------------------------------------
        #
        # knowledge_gateway.search() là điểm đi ra retrieval backend.
        #
        # Ở production hiện tại:
        #
        # query
        #   -> KnowledgeQdrantClient
        #   -> LlamaIndex retriever
        #   -> Qdrant hybrid hoặc dense search
        #
        # Kết quả trả về là list[KnowledgeDocument].
        # ----------------------------------------------------
        documents = await self._knowledge_gateway.search(query, limit=self._retrieve_limit)

        # ----------------------------------------------------
        # STEP 2: Lọc theo điểm liên quan
        # ----------------------------------------------------
        #
        # Qdrant/LlamaIndex trả về các ứng viên đã được xếp hạng.
        #
        # Bước này loại bỏ những document có score thấp hơn ngưỡng cấu
        # hình, để các match yếu không đi vào câu trả lời cuối.
        # ----------------------------------------------------
        accepted = [
            document for document in documents if document.score >= self._min_relevance_score
        ]

        # ----------------------------------------------------
        # STEP 3: Rerank các document đã qua ngưỡng
        # ----------------------------------------------------
        #
        # Retriever dùng để tìm candidate nhanh.
        #
        # Reranker chấm lại các candidate đã qua ngưỡng bằng cách nhìn cả
        # câu hỏi của user và nội dung document.
        #
        # Cách hiện tại:
        #
        # lexical overlap + semantic score ban đầu
        # ----------------------------------------------------
        reranked = self._reranker.rerank(query=query, documents=accepted)

        # ----------------------------------------------------
        # STEP 4: Tổng hợp câu trả lời
        # ----------------------------------------------------
        #
        # Synthesizer biến các document tốt nhất sau rerank thành một
        # payload câu trả lời.
        #
        # Cách hiện tại là extractive:
        #
        # không gọi LLM, chỉ ghép các đoạn có căn cứ tốt nhất và loại bỏ
        # nội dung trùng lặp.
        # ----------------------------------------------------
        synthesized = self._synthesizer.synthesize(reranked)

        # ----------------------------------------------------
        # STEP 5: Trả kết quả query
        # ----------------------------------------------------
        #
        # Giữ lại metadata cần cho logging và map response:
        #
        # - candidate_count: retrieval tìm được bao nhiêu document
        # - source_count: câu trả lời dùng bao nhiêu đoạn
        # - top_score: score retrieval cao nhất ban đầu
        # ----------------------------------------------------
        return KnowledgeAnswer(
            answer=synthesized.answer,
            candidate_count=len(documents),
            source_count=synthesized.source_count,
            top_score=max((document.score for document in documents), default=None),
        )


class FAQManager:
    """Điều phối câu trả lời FAQ mà không mutate booking context."""

    def __init__(
        self,
        *,
        knowledge_gateway: KnowledgeGateway | None,
        instruction_builder: InstructionBuilder,
        min_relevance_score: float = 0.45,
    ) -> None:
        self._knowledge_gateway = knowledge_gateway
        self._instruction_builder = instruction_builder
        self._query_service = (
            KnowledgeQueryService(
                knowledge_gateway=knowledge_gateway,
                min_relevance_score=min_relevance_score,
                retrieve_limit=6,
            )
            if knowledge_gateway is not None
            else None
        )

    async def answer(
        self,
        *,
        query: str,
        context: BookingContext,
    ) -> DialogResponse:
        """
        Trả lời một FAQ turn mà không thay đổi booking context.

        Luồng:

        query + context
          -> knowledge query service
          -> no-result hoặc grounded answer
          -> DialogResponse
        """

        # ----------------------------------------------------
        # STEP 1: Bắt đầu lượt FAQ
        # ----------------------------------------------------
        #
        # FAQ là một nhánh phụ của chat flow.
        #
        # Nhánh này trả lời câu hỏi nhưng vẫn giữ nguyên booking state
        # hiện tại để user có thể tiếp tục đặt lịch sau đó.
        # ----------------------------------------------------
        started_at = perf_counter()
        query_service = self._query_service

        # ----------------------------------------------------
        # STEP 2: Xử lý khi chưa có Knowledge Gateway
        # ----------------------------------------------------
        #
        # Nếu Qdrant/RAG đang tắt, trả về thông báo an toàn.
        #
        # Response được đánh dấu handled failure để chat turn vẫn nằm trong
        # kiểm soát và không lộ chi tiết hạ tầng cho user.
        # ----------------------------------------------------
        if query_service is None:
            self._log_failure("qdrant_disabled", started_at)
            return self._render_unavailable(context)

        # ----------------------------------------------------
        # STEP 3: Chạy RAG query flow
        # ----------------------------------------------------
        #
        # KnowledgeQueryService chịu trách nhiệm các bước RAG bên trong:
        #
        # retrieve
        #   -> threshold
        #   -> rerank
        #   -> synthesize
        #
        # FAQManager chỉ map kết quả sang DialogResponse.
        # ----------------------------------------------------
        try:
            result = await query_service.answer(query)
        except KnowledgeGatewayError:
            self._log_failure("knowledge_gateway_unavailable", started_at)
            return self._render_unavailable(context)

        # ----------------------------------------------------
        # STEP 4: Xử lý khi không có kết quả phù hợp
        # ----------------------------------------------------
        #
        # Retrieval có thể chạy thành công nhưng vẫn không có câu trả lời
        # dùng được sau threshold, deduplicate hoặc synthesize.
        #
        # Khi đó trả về câu "chưa đủ thông tin" thay vì đoán.
        # ----------------------------------------------------
        if not result.answer:
            trace_log(
                _LOGGER,
                logging.INFO,
                "[6] RAG",
                "no_result",
                operation="faq_retrieval",
                candidate_count=result.candidate_count,
                accepted_result_count=0,
                top_score=result.top_score,
                error_code="no_relevant_result",
                duration_ms=elapsed_ms(started_at),
            )
            return self._instruction_builder.build_faq_response(
                answer=_FAQ_NO_RESULT_TEXT,
                source_count=0,
                context=context,
                handled_failure=True,
            )

        # ----------------------------------------------------
        # STEP 5: Render FAQ response có căn cứ
        # ----------------------------------------------------
        #
        # Chỉ expose câu trả lời đã tổng hợp và số lượng source.
        #
        # Source path nội bộ, score, vector và lỗi provider được giữ bên
        # trong RAG layer.
        # ----------------------------------------------------
        trace_log(
            _LOGGER,
            logging.INFO,
            "[6] RAG",
            "completed",
            operation="faq_retrieval",
            candidate_count=result.candidate_count,
            accepted_result_count=result.source_count,
            top_score=result.top_score,
            duration_ms=elapsed_ms(started_at),
        )
        return self._instruction_builder.build_faq_response(
            answer=result.answer,
            source_count=result.source_count,
            context=context,
        )

    @staticmethod
    def _log_failure(error_code: str, started_at: float) -> None:
        # ----------------------------------------------------
        # STEP 1: Log lỗi FAQ/RAG theo dạng an toàn
        # ----------------------------------------------------
        #
        # Log chỉ chứa error_code và duration, không log query raw hoặc
        # nội dung retrieved document.
        # ----------------------------------------------------
        trace_log(
            _LOGGER,
            logging.WARNING,
            "[6] RAG",
            "failed",
            operation="faq_retrieval",
            error_code=error_code,
            duration_ms=elapsed_ms(started_at),
        )

    def _render_unavailable(self, context: BookingContext) -> DialogResponse:
        # ----------------------------------------------------
        # STEP 1: Render response fallback khi RAG unavailable
        # ----------------------------------------------------
        #
        # handled_failure=True cho biết bot đã xử lý lỗi có kiểm soát và
        # không nên tiếp tục route sang booking action khác.
        # ----------------------------------------------------
        return self._instruction_builder.build_faq_response(
            answer=_FAQ_UNAVAILABLE_TEXT,
            source_count=0,
            context=context,
            handled_failure=True,
        )


def _combined_score(
    query_terms: frozenset[str],
    document: KnowledgeDocument,
) -> tuple[float, float]:
    # ----------------------------------------------------
    # STEP 1: Kết hợp lexical score và semantic score
    # ----------------------------------------------------
    #
    # overlap đo độ khớp từ khóa với câu hỏi; document.score giữ điểm
    # semantic ban đầu từ retriever/Qdrant.
    # ----------------------------------------------------
    content_terms = _tokenize(document.content)
    overlap = len(query_terms & content_terms) / len(query_terms) if query_terms else 0.0
    return overlap, document.score


def _tokenize(text: str) -> frozenset[str]:
    # ----------------------------------------------------
    # STEP 1: Tokenize text đơn giản cho reranker
    # ----------------------------------------------------
    #
    # casefold() giúp so khớp không phân biệt hoa/thường và hỗ trợ tốt
    # hơn cho Unicode so với lower().
    # ----------------------------------------------------
    return frozenset(match.group(0).casefold() for match in _TOKEN_PATTERN.finditer(text))
