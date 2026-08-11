import httpx

from app.infrastructure.gemini_client import (
    GeminiClient,
    LLMMessage,
)

from app.rag.prompt import PromptBuilder
from app.rag.reranker import Reranker
from app.rag.retriever import Retriever


# ============================================================
# RAGService
# ============================================================
#
# Class này chịu trách nhiệm điều phối toàn bộ QUERY pipeline:
#
# User query
#     ↓
# Retriever
#     ↓
# Lấy top-k candidate chunks từ Qdrant
#     ↓
# Reranker
#     ↓
# Chọn top-n chunks liên quan nhất
#     ↓
# PromptBuilder
#     ↓
# Build prompt gồm context + question
#     ↓
# GeminiClient
#     ↓
# Gemini API
#     ↓
# Final answer
#
#
# Service này KHÔNG chịu trách nhiệm:
#
# - đọc file knowledge
# - chunk document
# - index dữ liệu vào Qdrant
# - tạo embedding cho toàn bộ knowledge base
#
# Những phần trên thuộc ingestion pipeline.
#
# ============================================================

class RAGService:

    # --------------------------------------------------------
    # System prompt
    # --------------------------------------------------------
    #
    # Đây là instruction ở cấp system gửi cho Gemini.
    #
    # Mục đích:
    #
    # - ép LLM chỉ dựa vào tài liệu
    # - hạn chế hallucination
    # - nếu context không đủ thì phải nói rõ
    #
    # --------------------------------------------------------

    _SYSTEM_PROMPT = (
        "Bạn là trợ lý hỏi đáp dựa trên tài liệu. "
        "Chỉ trả lời dựa trên context được cung cấp. "
        "Nếu context không đủ, hãy nói rõ rằng "
        "không tìm thấy đủ thông tin trong tài liệu."
    )


    # ========================================================
    # Constructor
    # ========================================================

    def __init__(
        self,
        retriever: Retriever,
        reranker: Reranker,
        prompt_builder: PromptBuilder,
        api_key: str,
        base_url: str,
        model: str,
        fallback_model: str | None = None,
        max_retries: int = 0,
    ) -> None:
        """
        Khởi tạo RAGService.

        Các dependency RAG được truyền từ bên ngoài:

        - retriever
        - reranker
        - prompt_builder

        Riêng Gemini client được tạo trực tiếp trong service
        để đơn giản hóa việc test hiện tại.
        """

        # ----------------------------------------------------
        # 1. Validate Gemini config
        # ----------------------------------------------------
        #
        # API key, base URL và model là những giá trị bắt buộc.
        #
        # Nếu thiếu thì fail sớm ngay lúc khởi tạo service,
        # thay vì chờ tới lúc gọi Gemini mới phát hiện lỗi.
        #
        # ----------------------------------------------------

        if not api_key.strip():
            raise ValueError(
                "Gemini API key cannot be empty."
            )

        if not base_url.strip():
            raise ValueError(
                "Gemini base URL cannot be empty."
            )

        if not model.strip():
            raise ValueError(
                "Gemini model cannot be empty."
            )


        # ----------------------------------------------------
        # 2. Lưu các RAG dependencies
        # ----------------------------------------------------
        #
        # Retriever:
        #
        # query
        #   ↓
        # embedding
        #   ↓
        # Qdrant search
        #
        #
        # Reranker:
        #
        # candidate chunks
        #   ↓
        # CrossEncoder
        #   ↓
        # reordered chunks
        #
        #
        # PromptBuilder:
        #
        # query + context
        #   ↓
        # final prompt
        #
        # ----------------------------------------------------

        self.retriever = retriever
        self.reranker = reranker
        self.prompt_builder = prompt_builder


        # ----------------------------------------------------
        # 3. Tạo HTTP client
        # ----------------------------------------------------
        #
        # GeminiClient hiện tại của project cần:
        #
        # httpx.AsyncClient
        #
        # để thực hiện HTTP request tới Gemini API.
        #
        # Client này được tạo một lần khi RAGService được tạo.
        #
        # KHÔNG tạo AsyncClient trong mỗi lần answer().
        #
        # ----------------------------------------------------

        self.http_client = httpx.AsyncClient()


        # ----------------------------------------------------
        # 4. Tạo Gemini client
        # ----------------------------------------------------
        #
        # Reuse class GeminiClient hiện có của project.
        #
        # Không viết lại logic gọi Gemini.
        #
        # GeminiClient đã chịu trách nhiệm:
        #
        # - gửi request
        # - model
        # - fallback model
        # - retry
        # - parse response
        #
        # ----------------------------------------------------

        self.gemini_client = GeminiClient(
            client=self.http_client,
            api_key=api_key,
            base_url=base_url,
            model=model,
            fallback_model=fallback_model,
            max_retries=max_retries,
        )


    # ========================================================
    # answer()
    # ========================================================

    async def answer(
        self,
        query: str,
        *,
        retrieve_top_k: int = 10,
        rerank_top_n: int = 3,
    ) -> str:
        """
        Chạy toàn bộ RAG query pipeline.

        Flow:

        query
          ↓
        retrieve top-k
          ↓
        rerank top-n
          ↓
        build prompt
          ↓
        Gemini
          ↓
        answer
        """

        # ----------------------------------------------------
        # STEP 1: Validate query
        # ----------------------------------------------------
        #
        # Không cho phép query rỗng.
        #
        # Ví dụ invalid:
        #
        # ""
        # "   "
        #
        # ----------------------------------------------------

        if not query.strip():
            raise ValueError(
                "Query cannot be empty."
            )


        # ----------------------------------------------------
        # STEP 2: Validate retrieve_top_k
        # ----------------------------------------------------
        #
        # retrieve_top_k =
        # số lượng candidate chunks lấy từ Qdrant.
        #
        # Ví dụ:
        #
        # retrieve_top_k = 10
        #
        # nghĩa là:
        #
        # Qdrant trả về tối đa 10 chunks
        # gần query nhất.
        #
        # ----------------------------------------------------

        if retrieve_top_k <= 0:
            raise ValueError(
                "retrieve_top_k must be greater than 0."
            )


        # ----------------------------------------------------
        # STEP 3: Validate rerank_top_n
        # ----------------------------------------------------
        #
        # rerank_top_n =
        # số lượng chunks cuối cùng đưa vào prompt.
        #
        # Ví dụ:
        #
        # Retriever:
        #     10 chunks
        #
        # Reranker:
        #     chọn 3 chunks tốt nhất
        #
        # ----------------------------------------------------

        if rerank_top_n <= 0:
            raise ValueError(
                "rerank_top_n must be greater than 0."
            )


        # ----------------------------------------------------
        # STEP 4: Retrieve candidate chunks
        # ----------------------------------------------------
        #
        # Query:
        #
        # "RAG là gì?"
        #
        #       ↓
        #
        # Retriever
        #
        #       ↓
        #
        # EmbeddingModel.embed_text(query)
        #
        #       ↓
        #
        # query vector
        #
        #       ↓
        #
        # Qdrant cosine search
        #
        #       ↓
        #
        # list[SearchResult]
        #
        #
        # Ví dụ:
        #
        # 10 candidate chunks
        #
        # ----------------------------------------------------

        candidates = self.retriever.retrieve(
            query=query,
            top_k=retrieve_top_k,
        )


        # ----------------------------------------------------
        # STEP 5: Rerank candidates
        # ----------------------------------------------------
        #
        # Retriever chủ yếu tìm nhanh candidate.
        #
        # Reranker sẽ xem trực tiếp:
        #
        # query + chunk text
        #
        # để đánh giá lại độ liên quan.
        #
        #
        # Ví dụ:
        #
        # 10 SearchResult
        #
        #       ↓
        #
        # CrossEncoder
        #
        #       ↓
        #
        # sort theo rerank_score
        #
        #       ↓
        #
        # top 3 RerankedResult
        #
        # ----------------------------------------------------

        reranked_results = self.reranker.rerank(
            query=query,
            results=candidates,
            top_n=rerank_top_n,
        )


        # ----------------------------------------------------
        # STEP 6: Build prompt
        # ----------------------------------------------------
        #
        # PromptBuilder nhận:
        #
        # - query
        # - reranked context
        #
        #
        # Ví dụ:
        #
        # CONTEXT:
        #
        # [Context 1]
        # ...
        #
        # [Context 2]
        # ...
        #
        # QUESTION:
        #
        # RAG là gì?
        #
        #
        # Sau đó trả về một string prompt hoàn chỉnh.
        #
        # ----------------------------------------------------

        prompt = self.prompt_builder.build(
            query=query,
            results=reranked_results,
        )


        # ----------------------------------------------------
        # STEP 7: Build messages cho Gemini
        # ----------------------------------------------------
        #
        # GeminiClient của project không nhận string trực tiếp.
        #
        # Nó nhận:
        #
        # list[LLMMessage]
        #
        #
        # Ta truyền 2 messages:
        #
        # 1. system
        #    → rule chung cho LLM
        #
        # 2. user
        #    → prompt RAG chứa context + query
        #
        # ----------------------------------------------------

        messages = [
            LLMMessage(
                role="system",
                content=self._SYSTEM_PROMPT,
            ),
            LLMMessage(
                role="user",
                content=prompt,
            ),
        ]


        # ----------------------------------------------------
        # STEP 8: Call Gemini
        # ----------------------------------------------------
        #
        # GeminiClient.generate() là async.
        #
        # Vì vậy:
        #
        # - phải dùng await
        # - answer() cũng phải là async
        #
        #
        # Kết quả trả về:
        #
        # LLMResponse
        #
        # chứa:
        #
        # response.content
        #
        # ----------------------------------------------------

        response = await self.gemini_client.generate(
            messages
        )


        # ----------------------------------------------------
        # STEP 9: Lấy text từ Gemini response
        # ----------------------------------------------------
        #
        # response.content có type:
        #
        # str | None
        #
        # Nên phải xử lý trường hợp None.
        #
        # .strip()
        #
        # để loại bỏ khoảng trắng/newline dư.
        #
        # ----------------------------------------------------

        answer = (
            response.content.strip()
            if response.content is not None
            else ""
        )


        # ----------------------------------------------------
        # STEP 10: Validate Gemini response
        # ----------------------------------------------------
        #
        # Nếu Gemini trả:
        #
        # None
        #
        # hoặc:
        #
        # ""
        #
        # thì xem là response không hợp lệ.
        #
        # ----------------------------------------------------

        if not answer:
            raise ValueError(
                "Gemini returned an empty RAG response."
            )


        # ----------------------------------------------------
        # STEP 11: Return final answer
        # ----------------------------------------------------

        return answer


    # ========================================================
    # close()
    # ========================================================

    async def close(self) -> None:
        """
        Đóng HTTP client khi application kết thúc.

        Vì RAGService tự tạo httpx.AsyncClient,
        nên chính RAGService cũng phải chịu trách nhiệm đóng nó.
        """

        await self.http_client.aclose()