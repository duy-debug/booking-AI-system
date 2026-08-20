from dataclasses import dataclass
from importlib import import_module

from app.rag_v1.vector_store import SearchResult

# ============================================================
# RerankedResult
# ============================================================
#
# Đây là kết quả sau khi CrossEncoder rerank.
#
# Nó giữ:
#
# - text
# - source
# - file_path
# - chunk_index
#
# Và giữ cả 2 score:
#
# retrieval_score
#     score ban đầu từ Qdrant
#
# rerank_score
#     score mới do CrossEncoder tính
#
# Điều này rất hữu ích để debug và so sánh:
#
# Retriever nghĩ chunk nào tốt?
# Reranker nghĩ chunk nào tốt?
# ============================================================

@dataclass
class RerankedResult:
    text: str
    source: str
    file_path: str
    chunk_index: int
    retrieval_score: float
    rerank_score: float


# ============================================================
# Reranker
# ============================================================
#
# Class này chịu trách nhiệm:
#
# query
#   +
# retrieved candidates
#       ↓
# CrossEncoder
#       ↓
# score từng query-document pair
#       ↓
# sort lại
#       ↓
# top-n relevant chunks
#
#
# Nó KHÔNG:
#
# - embedding query
# - search Qdrant
# - build prompt
# - gọi Gemini
#
# ============================================================

class Reranker:

    def __init__(
        self,
        model_name: str = "cross-encoder/ms-marco-MiniLM-L6-v2",
    ) -> None:
        """
        Khởi tạo CrossEncoder reranker.

        model_name:
            tên reranker model.
        """

        # ----------------------------------------------------
        # 1. Validate model name
        # ----------------------------------------------------

        if not model_name.strip():
            raise ValueError(
                "model_name cannot be empty"
            )


        # ----------------------------------------------------
        # 2. Lưu config
        # ----------------------------------------------------

        self.model_name = model_name


        # ----------------------------------------------------
        # 3. Load CrossEncoder
        # ----------------------------------------------------
        #
        # Model load một lần.
        #
        # Không load lại mỗi lần rerank vì rất tốn thời gian.
        # ----------------------------------------------------

        sentence_transformers_module = import_module("sentence_transformers")
        cross_encoder = sentence_transformers_module.CrossEncoder
        self.model = cross_encoder(
            model_name
        )


    def rerank(
        self,
        query: str,
        results: list[SearchResult],
        top_n: int = 3,
    ) -> list[RerankedResult]:
        """
        Rerank các kết quả retrieval.

        Flow:

        query + SearchResult[]
               ↓
        tạo query-document pairs
               ↓
        CrossEncoder.predict()
               ↓
        rerank score
               ↓
        sort score giảm dần
               ↓
        top-n RerankedResult
        """

        # ----------------------------------------------------
        # 1. Validate query
        # ----------------------------------------------------

        if not query.strip():
            raise ValueError(
                "Query cannot be empty"
            )


        # ----------------------------------------------------
        # 2. Validate top_n
        # ----------------------------------------------------

        if top_n <= 0:
            raise ValueError(
                "top_n must be greater than 0"
            )


        # ----------------------------------------------------
        # 3. Không có candidate
        # ----------------------------------------------------

        if not results:
            return []


        # ----------------------------------------------------
        # 4. Tạo query-document pairs
        # ----------------------------------------------------
        #
        # Ví dụ:
        #
        # query:
        #
        # "RAG là gì?"
        #
        # results:
        #
        # result 1
        # result 2
        #
        # →
        #
        # [
        #     ["RAG là gì?", result_1.text],
        #     ["RAG là gì?", result_2.text],
        # ]
        # ----------------------------------------------------

        pairs = [
            [
                query,
                result.text,
            ]
            for result in results
        ]


        # ----------------------------------------------------
        # 5. CrossEncoder chấm score
        # ----------------------------------------------------

        scores = self.model.predict(
            pairs
        )


        # ----------------------------------------------------
        # 6. Build RerankedResult
        # ----------------------------------------------------

        reranked_results: list[RerankedResult] = []


        for result, score in zip(
            results,
            scores,
            strict=False,
        ):

            reranked_result = RerankedResult(
                text=result.text,
                source=result.source,
                file_path=result.file_path,
                chunk_index=result.chunk_index,

                # Score từ Qdrant
                retrieval_score=result.score,

                # Score từ CrossEncoder
                rerank_score=float(score),
            )


            reranked_results.append(
                reranked_result
            )


        # ----------------------------------------------------
        # 7. Sort theo rerank_score
        # ----------------------------------------------------
        #
        # Score cao hơn đứng trước.
        # ----------------------------------------------------

        reranked_results.sort(
            key=lambda item: item.rerank_score,
            reverse=True,
        )


        # ----------------------------------------------------
        # 8. Return top-n
        # ----------------------------------------------------

        return reranked_results[:top_n]
