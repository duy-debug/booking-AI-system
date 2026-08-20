from app.rag_v1.embedding import EmbeddingModel
from app.rag_v1.vector_store import SearchResult, VectorStore

# ============================================================
# Retriever
# ============================================================
#
# Class này chịu trách nhiệm:
#
# user query
#     ↓
# embedding
#     ↓
# query vector
#     ↓
# vector search
#     ↓
# top-k relevant chunks
#
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
    ) -> None:
        """
        Khởi tạo Retriever.

        embedder:
            Chuyển query text thành embedding vector.

        vector_store:
            Nhận query vector và search các point
            gần nhất trong Qdrant.
        """

        # ----------------------------------------------------
        # 1. Lưu dependencies
        # ----------------------------------------------------

        self.embedder = embedder
        self.vector_store = vector_store


    def retrieve(
        self,
        query: str,
        top_k: int = 5,
    ) -> list[SearchResult]:
        """
        Retrieve các chunk liên quan nhất với query.

        Flow:

        query
          ↓
        embed query
          ↓
        query vector
          ↓
        search Qdrant
          ↓
        top-k SearchResult
        """

        # ----------------------------------------------------
        # 1. Validate query
        # ----------------------------------------------------
        #
        # Không cho query rỗng hoặc chỉ có whitespace.
        #
        # Ví dụ:
        #
        # ""
        # "   "
        #
        # đều không hợp lệ.
        # ----------------------------------------------------

        if not query.strip():
            raise ValueError(
                "Query cannot be empty"
            )


        # ----------------------------------------------------
        # 2. Validate top_k
        # ----------------------------------------------------
        #
        # top_k là số lượng kết quả muốn retrieve.
        #
        # Ví dụ:
        #
        # top_k = 5
        #
        # → lấy 5 chunk gần query nhất.
        # ----------------------------------------------------

        if top_k <= 0:
            raise ValueError(
                "top_k must be greater than 0"
            )


        # ----------------------------------------------------
        # 3. Embed query
        # ----------------------------------------------------
        #
        # Ví dụ:
        #
        # "RAG là gì?"
        #
        #        ↓
        #
        # EmbeddingModel
        #
        #        ↓
        #
        # [
        #     0.012,
        #     -0.031,
        #     ...
        # ]
        #
        # Với all-MiniLM-L6-v2:
        #
        # vector dimension = 384
        # ----------------------------------------------------

        query_vector = self.embedder.embed_text(
            query
        )


        # ----------------------------------------------------
        # 4. Search trong VectorStore
        # ----------------------------------------------------
        #
        # VectorStore sẽ:
        #
        # query vector
        #      ↓
        # Qdrant
        #      ↓
        # cosine similarity
        #      ↓
        # top-k points
        #      ↓
        # SearchResult[]
        # ----------------------------------------------------

        results = self.vector_store.search(
            query_vector=query_vector,
            limit=top_k,
        )


        # ----------------------------------------------------
        # 5. Return kết quả
        # ----------------------------------------------------

        return results
