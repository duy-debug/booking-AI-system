from app.rag_v1.embedding import EmbeddingModel
from app.rag_v1.fusion import rrf_merge
from app.rag_v1.keyword_search import BM25KeywordSearch
from app.rag_v1.vector_store import SearchResult, VectorStore

# ============================================================
# Retriever
# ============================================================
#
# Class này chịu trách nhiệm lấy candidate chunks cho RAG query.
#
# Trong bản hybrid:
#
# user query
#     ↓
# semantic search
#     ↓
# keyword search
#     ↓
# RRF merge
#     ↓
# top-k candidate chunks
#
# Nó KHÔNG:
#
# - load file
# - chunk document
# - index knowledge
# - build prompt
# - gọi LLM
#
# ============================================================


class Retriever:
    def __init__(
        self,
        embedder: EmbeddingModel,
        vector_store: VectorStore,
        keyword_search: BM25KeywordSearch | None = None,
    ) -> None:
        """
        Khởi tạo Retriever.

        embedder:
            Chuyển query text thành embedding vector.

        vector_store:
            Search semantic bằng vector similarity trong Qdrant.

        keyword_search:
            Search keyword bằng BM25.
            Nếu chưa truyền dependency này thì Retriever chạy semantic-only.
        """

        # ----------------------------------------------------
        # 1. Lưu dependencies
        # ----------------------------------------------------

        self.embedder = embedder
        self.vector_store = vector_store
        self.keyword_search_engine = keyword_search


    def retrieve(
        self,
        query: str,
        top_k: int = 5,
    ) -> list[SearchResult]:
        """
        Retrieve các chunk liên quan nhất với query.

        Flow hybrid:

        query
          ↓
        semantic_search()
          ↓
        keyword_search()
          ↓
        rrf_merge()
          ↓
        top-k SearchResult
        """

        # ----------------------------------------------------
        # 1. Validate input
        # ----------------------------------------------------

        self._validate_query(
            query
        )
        self._validate_top_k(
            top_k
        )


        # ----------------------------------------------------
        # 2. Semantic search
        # ----------------------------------------------------
        #
        # Đây là search theo NGỮ NGHĨA.
        #
        # query text
        #      ↓
        # embedding vector
        #      ↓
        # Qdrant cosine similarity
        #      ↓
        # semantic_results
        # ----------------------------------------------------

        semantic_results = self.semantic_search(
            query=query,
            top_k=top_k,
        )


        # ----------------------------------------------------
        # 3. Nếu chưa bật keyword search thì trả semantic-only
        # ----------------------------------------------------

        if self.keyword_search_engine is None:
            return semantic_results


        # ----------------------------------------------------
        # 4. Keyword search
        # ----------------------------------------------------
        #
        # Đây là search theo TỪ KHÓA.
        #
        # query text
        #      ↓
        # tokenize
        #      ↓
        # BM25
        #      ↓
        # keyword_results
        # ----------------------------------------------------

        keyword_results = self.keyword_search(
            query=query,
            top_k=top_k,
        )


        # ----------------------------------------------------
        # 5. RRF merge
        # ----------------------------------------------------
        #
        # Đây là bước GỘP hybrid search.
        #
        # semantic_results
        #      ↓
        # keyword_results
        #      ↓
        # RRF
        #      ↓
        # final top-k candidate chunks
        # ----------------------------------------------------

        return rrf_merge(
            semantic_results=semantic_results,
            keyword_results=keyword_results,
            limit=top_k,
        )


    def semantic_search(
        self,
        query: str,
        top_k: int,
    ) -> list[SearchResult]:
        """
        Semantic search: search theo ý nghĩa bằng embedding vector.
        """

        # ----------------------------------------------------
        # 1. Embed query
        # ----------------------------------------------------

        query_vector = self.embedder.embed_text(
            query
        )


        # ----------------------------------------------------
        # 2. Search vector trong Qdrant
        # ----------------------------------------------------

        return self.vector_store.search(
            query_vector=query_vector,
            limit=top_k,
        )


    def keyword_search(
        self,
        query: str,
        top_k: int,
    ) -> list[SearchResult]:
        """
        Keyword search: search theo từ khóa bằng BM25.
        """

        if self.keyword_search_engine is None:
            return []

        return self.keyword_search_engine.search(
            query=query,
            limit=top_k,
        )


    def _validate_query(
        self,
        query: str,
    ) -> None:
        """
        Validate query trước khi retrieve.
        """

        if not query.strip():
            raise ValueError(
                "Query cannot be empty"
            )


    def _validate_top_k(
        self,
        top_k: int,
    ) -> None:
        """
        Validate số lượng kết quả muốn retrieve.
        """

        if top_k <= 0:
            raise ValueError(
                "top_k must be greater than 0"
            )
