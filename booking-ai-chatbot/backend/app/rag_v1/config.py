from dataclasses import dataclass

# ============================================================
# RAGConfig
# ============================================================
#
# Gom toàn bộ cấu hình RAG vào một nơi.
#
# Nếu sau này muốn đổi model, chunk size, overlap, collection
# hoặc top_k/top_n thì chỉ cần nhìn vào config này thay vì đi
# qua từng constructor riêng lẻ.
# ============================================================


@dataclass(frozen=True)
class RAGConfig:
    embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    normalize_embeddings: bool = True

    chunk_size: int = 1000
    chunk_overlap: int = 200

    qdrant_path: str = "qdrant_data"
    collection_name: str = "knowledge"
    vector_size: int = 384

    retrieve_top_k: int = 20
    rerank_top_n: int = 5

    recreate_collection_on_index: bool = False
    delete_existing_sources_on_index: bool = True

    def __post_init__(self) -> None:
        # ----------------------------------------------------
        # 1. Validate embedding config
        # ----------------------------------------------------

        if not self.embedding_model_name.strip():
            raise ValueError(
                "embedding_model_name cannot be empty"
            )


        # ----------------------------------------------------
        # 2. Validate chunking config
        # ----------------------------------------------------

        if self.chunk_size <= 0:
            raise ValueError(
                "chunk_size must be greater than 0"
            )

        if self.chunk_overlap < 0:
            raise ValueError(
                "chunk_overlap cannot be negative"
            )

        if self.chunk_overlap >= self.chunk_size:
            raise ValueError(
                "chunk_overlap must be smaller than chunk_size"
            )


        # ----------------------------------------------------
        # 3. Validate Qdrant config
        # ----------------------------------------------------

        if not self.qdrant_path.strip():
            raise ValueError(
                "qdrant_path cannot be empty"
            )

        if not self.collection_name.strip():
            raise ValueError(
                "collection_name cannot be empty"
            )

        if self.vector_size <= 0:
            raise ValueError(
                "vector_size must be greater than 0"
            )


        # ----------------------------------------------------
        # 4. Validate query config
        # ----------------------------------------------------

        if self.retrieve_top_k <= 0:
            raise ValueError(
                "retrieve_top_k must be greater than 0"
            )

        if self.rerank_top_n <= 0:
            raise ValueError(
                "rerank_top_n must be greater than 0"
            )
