
from pathlib import Path

from app.rag.loader import DocumentLoader
from app.rag.chunker import DocumentChunker
from app.rag.embedding import EmbeddingModel
from app.rag.vector_store import VectorStore


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


    def index_directory(
        self,
        directory_path: str | Path,
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

        self.vector_store.create_collection()


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