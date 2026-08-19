"""Offline pipeline để load, chunk, embed và ghi knowledge document."""

import argparse
from collections.abc import Sequence
from importlib import import_module
import os
from pathlib import Path
import sys
from typing import cast

from app.infrastructure.context_store import Settings
from app.knowledge.embeddings.llamaindex_adapter import build_llamaindex_embedding
from app.knowledge.embeddings.sentence_transformer import SentenceTransformerEmbedding
from app.knowledge.index.chunker import KnowledgeChunk, SectionAwareMarkdownChunker
from app.knowledge.index.errors import (
    EmptyKnowledgeDocumentError,
    InvalidIndexingSourceError,
    KnowledgeIndexingError,
)
from app.knowledge.index.loader import MarkdownDocument, MarkdownKnowledgeLoader
from app.knowledge.index.writer import (
    IndexEmbedding,
    IndexingSummary,
    ensure_collection,
    point_from_chunk,
    point_id_for_chunk,
    source_filter,
)
from app.knowledge.stores.qdrant import (
    QdrantIndexClient,
    build_qdrant_client,
    build_qdrant_vector_store,
    normalize_collection_name,
)


def index_knowledge_document(
    *,
    source: Path,
    embedding: IndexEmbedding,
    client: QdrantIndexClient,
    collection_name: str,
    recreate: bool = False,
    hybrid_enabled: bool = False,
) -> IndexingSummary:
    """
    Chạy pipeline index offline cho một Markdown document.

    Luồng:

    markdown file
      -> đọc text an toàn
      -> tách thành chunk
      -> embed chunk
      -> index dense hoặc hybrid
      -> Qdrant collection
    """

    # ----------------------------------------------------
    # STEP 1: Kiểm tra collection và source
    # ----------------------------------------------------
    #
    # Collection name phải dùng được với Qdrant.
    #
    # Source phải là một Markdown file thật. Loader sẽ kiểm tra sâu
    # hơn về path, size, encoding và extension sau bước check nhanh này.
    # ----------------------------------------------------
    normalized_collection = normalize_collection_name(collection_name)
    source_path = source.resolve()
    if not source_path.is_file():
        raise InvalidIndexingSourceError("Knowledge source must be an existing regular file.")

    # ----------------------------------------------------
    # STEP 2: Đọc Markdown document
    # ----------------------------------------------------
    #
    # MarkdownKnowledgeLoader đọc text UTF-8 và trả về MarkdownDocument
    # với logical source path an toàn.
    #
    # Source được lưu trong Qdrant payload để lần re-index sau có thể
    # thay thế các chunk cũ của cùng một file.
    # ----------------------------------------------------
    loader = MarkdownKnowledgeLoader(source_path.parent)
    document = loader.load(Path(source_path.name))

    # ----------------------------------------------------
    # STEP 3: Tách chunk từ Markdown
    # ----------------------------------------------------
    #
    # SectionAwareMarkdownChunker giữ context của heading và tạo chunk
    # id deterministic.
    #
    # Chunk deterministic giúp re-index ổn định và dễ test hơn.
    # ----------------------------------------------------
    chunks = SectionAwareMarkdownChunker().chunk(document)
    if not chunks:
        raise EmptyKnowledgeDocumentError("Knowledge source produced no indexable chunks.")

    # ----------------------------------------------------
    # STEP 4: Embed các chunk
    # ----------------------------------------------------
    #
    # Mỗi chunk content được chuyển thành một dense vector.
    #
    # Số vector phải khớp chính xác với số chunk, nếu không indexing sẽ
    # ghi lệch cặp content/vector.
    # ----------------------------------------------------
    vectors = embedding.embed_documents([chunk.content for chunk in chunks])
    if len(vectors) != len(chunks):
        raise KnowledgeIndexingError(
            "Embedding output count does not match the knowledge chunk count."
        )
    vector_dimension = embedding.dimension
    if any(len(vector) != vector_dimension for vector in vectors):
        raise KnowledgeIndexingError("Embedding output contains an inconsistent vector dimension.")

    # ----------------------------------------------------
    # STEP 5: Chọn chiến lược indexing
    # ----------------------------------------------------
    #
    # Dense indexing ghi trực tiếp Qdrant point kèm vector.
    #
    # Hybrid indexing đi qua LlamaIndex QdrantVectorStore để Qdrant có
    # thể lưu và query dense + sparse vector cùng lúc.
    # ----------------------------------------------------
    if hybrid_enabled:
        _index_knowledge_document_hybrid(
            document=document,
            chunks=chunks,
            embedding=embedding,
            client=client,
            collection_name=normalized_collection,
            recreate=recreate,
        )
        return IndexingSummary(
            collection_name=normalized_collection,
            source=document.source,
            chunk_count=len(chunks),
            vector_dimension=vector_dimension,
        )

    # ----------------------------------------------------
    # STEP 6: Đảm bảo dense collection tồn tại
    # ----------------------------------------------------
    #
    # Dense mode cần một collection cosine vector không đặt tên.
    #
    # Collection tương thích sẽ được tái sử dụng. Collection không tương
    # thích sẽ fail trừ khi caller truyền recreate=True.
    # ----------------------------------------------------
    ensure_collection(
        client=client,
        collection_name=normalized_collection,
        vector_dimension=vector_dimension,
        recreate=recreate,
    )

    # ----------------------------------------------------
    # STEP 7: Thay thế chunk cũ của cùng source
    # ----------------------------------------------------
    #
    # Re-index một file không được tạo duplicate chunk cũ.
    #
    # Vì vậy ta xóa các point cùng logical source trước khi insert bộ
    # chunk mới.
    # ----------------------------------------------------
    client.delete(
        collection_name=normalized_collection,
        points_selector=source_filter(document.source),
        wait=True,
    )

    # ----------------------------------------------------
    # STEP 8: Upsert dense points
    # ----------------------------------------------------
    #
    # Mỗi cặp KnowledgeChunk và vector trở thành một Qdrant PointStruct
    # có metadata content trong payload.
    # ----------------------------------------------------
    points = [
        point_from_chunk(chunk=chunk, vector=vector)
        for chunk, vector in zip(chunks, vectors, strict=True)
    ]
    client.upsert(
        collection_name=normalized_collection,
        points=points,
        wait=True,
    )

    # ----------------------------------------------------
    # STEP 9: Trả IndexingSummary
    # ----------------------------------------------------
    #
    # CLI và test dùng summary nhỏ này để xác nhận dữ liệu đã index mà
    # không expose raw vector hoặc payload đầy đủ.
    # ----------------------------------------------------
    return IndexingSummary(
        collection_name=normalized_collection,
        source=document.source,
        chunk_count=len(chunks),
        vector_dimension=vector_dimension,
    )


def _index_knowledge_document_hybrid(
    *,
    document: MarkdownDocument,
    chunks: list[KnowledgeChunk],
    embedding: IndexEmbedding,
    client: QdrantIndexClient,
    collection_name: str,
    recreate: bool,
) -> None:
    """Index chunk qua LlamaIndex để Qdrant lưu dense và sparse vector cùng nhau."""
    # ----------------------------------------------------
    # STEP 1: Kiểm tra adapter embedding cho hybrid
    # ----------------------------------------------------
    #
    # Hybrid indexing dùng LlamaIndex nên embedding object phải adapter
    # được sang LlamaIndex embed model.
    # ----------------------------------------------------
    if not isinstance(embedding, SentenceTransformerEmbedding):
        raise KnowledgeIndexingError(
            "Hybrid indexing requires a SentenceTransformerEmbedding-backed embedder."
        )

    # ----------------------------------------------------
    # STEP 2: Thay thế dữ liệu source cũ
    # ----------------------------------------------------
    #
    # Nếu collection đã tồn tại, xóa các chunk thuộc source hiện tại.
    #
    # Nếu recreate=True, xóa cả collection và để LlamaIndex/Qdrant tạo
    # lại hybrid collection.
    # ----------------------------------------------------
    existing_collection = client.collection_exists(collection_name)
    if existing_collection and recreate:
        client.delete_collection(collection_name)
        existing_collection = False
    if existing_collection:
        client.delete(
            collection_name=collection_name,
            points_selector=source_filter(document.source),
            wait=True,
        )

    # ----------------------------------------------------
    # STEP 3: Tạo hybrid vector store
    # ----------------------------------------------------
    #
    # enable_hybrid=True báo cho Qdrant adapter của LlamaIndex chuẩn bị
    # hành vi lưu/truy vấn dense + sparse.
    # ----------------------------------------------------
    vector_store = build_qdrant_vector_store(
        client=client,
        collection_name=collection_name,
        enable_hybrid=True,
    )

    # ----------------------------------------------------
    # STEP 4: Tạo LlamaIndex nodes
    # ----------------------------------------------------
    #
    # TextNode chứa chunk text và metadata payload cần dùng lại ở bước
    # retrieval.
    # ----------------------------------------------------
    core_module = import_module("llama_index.core")
    schema_module = import_module("llama_index.core.schema")
    storage_context = getattr(core_module, "StorageContext").from_defaults(
        vector_store=vector_store
    )
    index = getattr(core_module, "VectorStoreIndex")(
        storage_context=storage_context,
        nodes=[],
        embed_model=build_llamaindex_embedding(embedding),
    )
    text_node = getattr(schema_module, "TextNode")
    nodes = [
        text_node(
            id_=point_id_for_chunk(chunk.chunk_id),
            text=chunk.content,
            metadata={
                "chunk_id": chunk.chunk_id,
                "source": chunk.source,
                "section": chunk.section,
                "chunk_index": chunk.chunk_index,
            },
        )
        for chunk in chunks
    ]

    # ----------------------------------------------------
    # STEP 5: Insert node vào index
    # ----------------------------------------------------
    #
    # LlamaIndex xử lý embedding, sparse representation và ghi vào
    # Qdrant thông qua vector store đã cấu hình.
    # ----------------------------------------------------
    index.insert_nodes(nodes)


def settings_from_environment() -> Settings:
    """Đọc cấu hình phục vụ indexing từ environment hiện tại."""
    # ----------------------------------------------------
    # STEP 1: Đọc và kiểm tra cấu hình Qdrant
    # ----------------------------------------------------
    #
    # CLI index chạy độc lập với FastAPI, nên nó lấy cấu hình trực tiếp
    # từ environment thay vì dependency injection.
    # ----------------------------------------------------
    raw_port = os.getenv("QDRANT_PORT", "6333")
    try:
        port = int(raw_port)
    except ValueError as error:
        raise ValueError("Qdrant port must be an integer.") from error
    host = os.getenv("QDRANT_HOST", "localhost").strip()
    if not host:
        raise ValueError("Qdrant host must not be empty.")
    if (
        "://" in host
        or "/" in host
        or "@" in host
        or any(character.isspace() for character in host)
    ):
        raise ValueError("Qdrant host must be a hostname or IP address.")
    if not 1 <= port <= 65535:
        raise ValueError("Qdrant port must be between 1 and 65535.")

    # ----------------------------------------------------
    # STEP 2: Đọc cấu hình embedding và hybrid search
    # ----------------------------------------------------
    #
    # RAG_HYBRID_ENABLED bật đường indexing qua LlamaIndex để Qdrant có
    # thể lưu sparse vector phục vụ hybrid retrieval.
    # ----------------------------------------------------
    hybrid_enabled = os.getenv("RAG_HYBRID_ENABLED", "false").strip().casefold() in {
        "1",
        "true",
        "yes",
        "on",
    }
    return Settings(
        pos_base_url=os.getenv("BOOKING_API_URL", "http://localhost:8000"),
        embedding_model_name=os.getenv(
            "EMBED_MODEL_NAME",
            "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        ),
        qdrant_host=host,
        qdrant_port=port,
        qdrant_api_key=os.getenv("QDRANT_API_KEY") or None,
        qdrant_collection=os.getenv("QDRANT_COLLECTION", "kb_chunks"),
        rag_hybrid_enabled=hybrid_enabled,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("knowledge/README.md"),
        help="One Markdown knowledge file to index.",
    )
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Explicitly delete and recreate an existing collection.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Chạy command index offline một cách tường minh."""
    # ----------------------------------------------------
    # STEP 1: Parse tham số CLI
    # ----------------------------------------------------
    #
    # CLI hiện nhận một file Markdown và flag recreate để chủ động xóa
    # collection cũ khi cần rebuild index.
    # ----------------------------------------------------
    arguments = _parser().parse_args(argv)
    try:
        # ------------------------------------------------
        # STEP 2: Tạo dependency runtime cho indexing
        # ------------------------------------------------
        #
        # Tạo settings, embedding model và Qdrant client giống production
        # nhưng chạy trong command offline.
        # ------------------------------------------------
        settings = settings_from_environment()
        embedding = SentenceTransformerEmbedding(settings.embedding_model_name)
        client = build_qdrant_client(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
            api_key=settings.qdrant_api_key,
        )
        summary = index_knowledge_document(
            source=arguments.source,
            embedding=embedding,
            client=cast(QdrantIndexClient, client),
            collection_name=settings.qdrant_collection,
            recreate=arguments.recreate,
            hybrid_enabled=settings.rag_hybrid_enabled,
        )
    except (KnowledgeIndexingError, ValueError) as error:
        # ------------------------------------------------
        # STEP 3: Trả lỗi CLI dễ đọc
        # ------------------------------------------------
        #
        # Các lỗi expected được in ra stderr và trả exit code 1 để script
        # CI/CD hoặc developer biết indexing thất bại.
        # ------------------------------------------------
        print(f"Indexing failed: {error}", file=sys.stderr)
        return 1

    # ----------------------------------------------------
    # STEP 4: In summary không nhạy cảm
    # ----------------------------------------------------
    #
    # Không in raw vector/payload; chỉ in collection, source, số chunk và
    # dimension để xác nhận index đã chạy.
    # ----------------------------------------------------
    print(
        "Indexed "
        f"collection={summary.collection_name} "
        f"source={summary.source} "
        f"chunks={summary.chunk_count} "
        f"dimension={summary.vector_dimension}"
    )
    return 0
