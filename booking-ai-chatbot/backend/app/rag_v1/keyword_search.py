import re

from rank_bm25 import BM25Okapi

from app.rag_v1.vector_store import SearchResult, VectorStore, payload_text

# ============================================================
# Keyword Search
# ============================================================
#
# File này chịu trách nhiệm search theo TỪ KHÓA.
#
# Điểm khác với semantic search:
#
# - keyword search nhìn vào chữ xuất hiện trong document
# - không cần embedding
# - không cần query vector
# - dùng thư viện BM25Okapi để chấm điểm keyword relevance
#
# ============================================================


class BM25KeywordSearch:
    def __init__(
        self,
        vector_store: VectorStore,
        corpus_limit: int = 1000,
    ) -> None:
        """
        Khởi tạo BM25 keyword search.

        vector_store:
            Dùng để lấy payload text đã được lưu trong Qdrant.

        corpus_limit:
            Số lượng point tối đa lấy từ Qdrant để build BM25 corpus.
            Bản này ưu tiên đơn giản, nên build BM25 trực tiếp lúc search.
        """

        # ----------------------------------------------------
        # 1. Validate corpus_limit
        # ----------------------------------------------------

        if corpus_limit <= 0:
            raise ValueError(
                "corpus_limit must be greater than 0"
            )


        # ----------------------------------------------------
        # 2. Lưu dependencies
        # ----------------------------------------------------

        self.vector_store = vector_store
        self.corpus_limit = corpus_limit


    def search(
        self,
        query: str,
        limit: int = 5,
    ) -> list[SearchResult]:
        """
        Search theo keyword bằng BM25.

        Flow:

        query text
             ↓
        tokenize query
             ↓
        scroll payload text từ Qdrant
             ↓
        BM25Okapi chấm điểm từng chunk
             ↓
        trả về top-k SearchResult
        """

        # ----------------------------------------------------
        # 1. Validate input
        # ----------------------------------------------------

        if not query.strip():
            raise ValueError(
                "query cannot be empty"
            )

        if limit <= 0:
            raise ValueError(
                "limit must be greater than 0"
            )


        # ----------------------------------------------------
        # 2. Tokenize query
        # ----------------------------------------------------

        query_tokens = _tokenize(
            query
        )

        if not query_tokens:
            return []


        # ----------------------------------------------------
        # 3. Lấy payload text từ Qdrant
        # ----------------------------------------------------
        #
        # Qdrant vẫn là nơi lưu chunk text.
        #
        # Nhưng logic keyword search nằm ở file này,
        # không đặt trong VectorStore nữa.
        # VectorStore chỉ còn trách nhiệm vector/semantic search.
        # ----------------------------------------------------

        records, _ = self.vector_store.client.scroll(
            collection_name=self.vector_store.collection_name,
            limit=self.corpus_limit,
            with_payload=True,
            with_vectors=False,
        )


        # ----------------------------------------------------
        # 4. Build corpus cho BM25
        # ----------------------------------------------------

        searchable_results: list[SearchResult] = []
        tokenized_corpus: list[list[str]] = []

        for record in records:
            payload = record.payload or {}

            # ------------------------------------------------
            # Lấy text chunk từ payload
            # ------------------------------------------------
            #
            # BM25 cần nội dung text để build corpus.
            #
            # Qdrant hiện có thể chứa:
            #
            # - text:
            #     schema mới do RAG v1 upsert
            #
            # - content:
            #     schema cũ hoặc dữ liệu đã index trước đó
            #
            # Nếu không fallback sang content, keyword search
            # sẽ không thấy những chunk như "Bãi đậu xe".
            # ------------------------------------------------

            text = payload_text(
                payload
            )

            if not isinstance(text, str) or not text.strip():
                continue

            tokens = _tokenize(
                text
            )

            if not tokens:
                continue

            tokenized_corpus.append(
                tokens
            )
            searchable_results.append(
                SearchResult(
                    text=text,
                    source=str(
                        payload.get(
                            "source",
                            "",
                        )
                    ),
                    file_path=str(
                        payload.get(
                            "file_path",
                            "",
                        )
                    ),
                    chunk_index=int(
                        payload.get(
                            "chunk_index",
                            -1,
                        )
                    ),
                    score=0.0,
                )
            )

        if not searchable_results:
            return []


        # ----------------------------------------------------
        # 5. BM25Okapi chấm điểm và sort top-k
        # ----------------------------------------------------
        #
        # Đây là đoạn dùng thư viện BM25 thật sự:
        #
        # BM25Okapi(tokenized_corpus)
        # get_scores(query_tokens)
        # ----------------------------------------------------

        bm25 = BM25Okapi(
            tokenized_corpus
        )
        scores = bm25.get_scores(
            query_tokens
        )

        scored_results: list[SearchResult] = []

        for result, tokens, score in zip(
            searchable_results,
            tokenized_corpus,
            scores,
            strict=True,
        ):
            bm25_score = float(
                score
            )

            # ------------------------------------------------
            # Giữ lại chunk match keyword trực tiếp
            # ------------------------------------------------
            #
            # BM25 có thể trả 0.0 khi corpus nhỏ hoặc term xuất hiện
            # chưa đủ để tạo IDF dương.
            #
            # Nếu chỉ lọc score > 0.0, các câu rõ ràng như:
            #
            # "bãi đậu xe"
            #
            # vẫn có thể bị loại khỏi keyword_results.
            #
            # Vì vậy:
            #
            # - ưu tiên score BM25 nếu score dương
            # - fallback bằng số token query trùng với chunk
            #
            # Fallback này chỉ nằm trong keyword search,
            # không thay đổi semantic search hay RRF.
            # ------------------------------------------------

            matched_tokens = {
                token
                for token in query_tokens
                if token in tokens
            }

            if bm25_score <= 0.0 and not matched_tokens:
                continue

            final_score = bm25_score

            if final_score <= 0.0:
                final_score = float(
                    len(matched_tokens)
                )

            scored_results.append(
                SearchResult(
                    text=result.text,
                    source=result.source,
                    file_path=result.file_path,
                    chunk_index=result.chunk_index,
                    score=final_score,
                )
            )

        scored_results.sort(
            key=lambda item: item.score,
            reverse=True,
        )

        return scored_results[:limit]


def _tokenize(
    text: str,
) -> list[str]:
    """
    Tokenize đơn giản cho BM25.

    Dùng \\w+ để vẫn bắt được chữ tiếng Việt ở mức cơ bản.
    """

    return re.findall(
        r"\w+",
        text.casefold(),
    )
