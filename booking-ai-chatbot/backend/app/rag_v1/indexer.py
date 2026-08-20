
from pathlib import Path

from app.rag_v1.chunker import DocumentChunker
from app.rag_v1.config import RAGConfig
from app.rag_v1.embedding import EmbeddingModel
from app.rag_v1.loader import DocumentLoader
from app.rag_v1.vector_store import VectorStore

# ============================================================
# KnowledgeIndexer
# ============================================================
#
# Class này chịu trách nhiệm orchestration pipeline indexing:
#
# knowledge files
#      ↓
# DocumentLoader
#      ↓
# Document[]
#      ↓
# DocumentChunker
#      ↓
# Chunk[]
#      ↓
# EmbeddingModel
#      ↓
# Vector[]
#      ↓
# VectorStore
#      ↓
# Qdrant
#
#
# Indexer KHÔNG tự:
#
# - đọc file
# - chunk text
# - tạo embedding
# - gọi Qdrant API trực tiếp
#
# Nó chỉ gọi các component tương ứng theo đúng thứ tự.
# ============================================================

class KnowledgeIndexer:

    def __init__(
        self,
        loader: DocumentLoader,
        chunker: DocumentChunker,
        embedder: EmbeddingModel,
        vector_store: VectorStore,
        config: RAGConfig | None = None,
    ) -> None:
        """
        Khởi tạo KnowledgeIndexer.

        Các dependency được truyền từ bên ngoài:

        loader
            đọc file → Document

        chunker
            Document → Chunk

        embedder
            Chunk → vector

        vector_store
            lưu vector + metadata vào Qdrant
        """

        # ----------------------------------------------------
        # 1. Lưu dependencies
        # ----------------------------------------------------

        self.loader = loader
        self.chunker = chunker
        self.embedder = embedder
        self.vector_store = vector_store
        self.config = config or RAGConfig()


    def index_directory(
        self,
        directory_path: str | Path,
        *,
        recreate_collection: bool | None = None,
        delete_existing_sources: bool | None = None,
    ) -> int:
        """
        Index toàn bộ knowledge trong một directory.

        Flow:

        directory
            ↓
        load documents
            ↓
        chunk documents
            ↓
        embed chunks
            ↓
        create collection
            ↓
        upsert vào Qdrant
            ↓
        return số chunk đã index
        """

        # ----------------------------------------------------
        # 1. Load tất cả documents
        # ----------------------------------------------------

        should_recreate_collection = (
            self.config.recreate_collection_on_index
            if recreate_collection is None
            else recreate_collection
        )

        should_delete_existing_sources = (
            self.config.delete_existing_sources_on_index
            if delete_existing_sources is None
            else delete_existing_sources
        )

        documents = self.loader.load_directory(
            directory_path
        )


        # ----------------------------------------------------
        # 2. Nếu không có document
        # ----------------------------------------------------
        #
        # Với loader hiện tại, folder có thể tồn tại
        # nhưng không có file extension được support.
        # ----------------------------------------------------

        if not documents:
            return 0


        # ----------------------------------------------------
        # 3. Chunk documents
        # ----------------------------------------------------

        chunks = self.chunker.chunk_documents(
            documents
        )


        # ----------------------------------------------------
        # 4. Nếu không tạo được chunk
        # ----------------------------------------------------

        if not chunks:
            return 0


        # ----------------------------------------------------
        # 5. Embed toàn bộ chunks
        # ----------------------------------------------------
        #
        # Mapping:
        #
        # chunks[0] ↔ vectors[0]
        # chunks[1] ↔ vectors[1]
        # ...
        # ----------------------------------------------------

        vectors = self.embedder.embed_chunks(
            chunks
        )


        # ----------------------------------------------------
        # 6. Defensive check
        # ----------------------------------------------------
        #
        # embed_chunks() về lý thuyết phải trả cùng số lượng.
        # Nhưng Indexer vẫn có thể kiểm tra để lỗi rõ ràng hơn.
        # ----------------------------------------------------

        if len(chunks) != len(vectors):
            raise RuntimeError(
                "Embedding count does not match chunk count"
            )


        # ----------------------------------------------------
        # 7. Đảm bảo collection tồn tại
        # ----------------------------------------------------

        if should_recreate_collection:
            self.vector_store.recreate_collection()

        else:
            self.vector_store.create_collection()

            if should_delete_existing_sources:
                self.vector_store.delete_sources(
                    [
                        document.source
                        for document in documents
                    ]
                )


        # ----------------------------------------------------
        # 8. Lưu chunks + vectors vào Qdrant
        # ----------------------------------------------------

        self.vector_store.upsert(
            chunks,
            vectors,
        )


        # ----------------------------------------------------
        # 9. Return số chunk đã index
        # ----------------------------------------------------

        return len(chunks)


def build_indexer(
    config: RAGConfig | None = None,
) -> KnowledgeIndexer:
    """
    Tạo KnowledgeIndexer từ RAGConfig.

    Hàm này giúp code bên ngoài không phải tự nhớ:

    - chunk_size nằm ở DocumentChunker
    - model_name nằm ở EmbeddingModel
    - qdrant_path nằm ở VectorStore
    """

    # ----------------------------------------------------
    # 1. Dùng config mặc định nếu caller không truyền
    # ----------------------------------------------------

    config = config or RAGConfig()


    # ----------------------------------------------------
    # 2. Wire các component theo đúng flow RAG
    # ----------------------------------------------------

    return KnowledgeIndexer(
        loader=DocumentLoader(),
        chunker=DocumentChunker(
            chunk_size=config.chunk_size,
            chunk_overlap=config.chunk_overlap,
        ),
        embedder=EmbeddingModel(
            model_name=config.embedding_model_name,
            normalize_embeddings=config.normalize_embeddings,
        ),
        vector_store=VectorStore(
            path=config.qdrant_path,
            collection_name=config.collection_name,
            vector_size=config.vector_size,
        ),
        config=config,
    )
