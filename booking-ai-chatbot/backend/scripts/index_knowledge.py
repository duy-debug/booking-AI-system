from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from qdrant_client import QdrantClient

# Script này là entrypoint ingestion knowledge cho chatbot runtime.
# Nó tồn tại để index lại toàn bộ file trong folder knowledge vào đúng Qdrant server
# và đúng collection mà API chatbot đang retrieve, tránh lỗi index nhầm sang local
# qdrant_data/knowledge trong khi runtime lại đọc localhost:6333/kb_chunks.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.rag_v1.chunker import DocumentChunker  # noqa: E402
from app.rag_v1.config import RAGConfig  # noqa: E402
from app.rag_v1.embedding import EmbeddingModel  # noqa: E402
from app.rag_v1.indexer import KnowledgeIndexer  # noqa: E402
from app.rag_v1.loader import DocumentLoader  # noqa: E402
from app.rag_v1.vector_store import VectorStore  # noqa: E402


# Parse biến môi trường boolean cho các flag ingestion tùy chọn.
# Dùng chung format phổ biến để chạy được cả local và CI/script shell.
def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


# Parse biến môi trường dạng số nguyên để cấu hình port Qdrant.
# Nếu biến chưa khai báo thì dùng default giống runtime chatbot.
def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return int(value)


# Khai báo CLI cho thao tác index thủ công.
# Các flag nguy hiểm như recreate collection phải được bật rõ ràng.
def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Index files from the knowledge folder into the same Qdrant server "
            "and collection that chatbot runtime reads."
        )
    )
    parser.add_argument(
        "--knowledge-dir",
        default=str(BACKEND_ROOT / "knowledge"),
        help="Folder containing knowledge files. Default: knowledge",
    )
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Drop and recreate the target collection before indexing.",
    )
    parser.add_argument(
        "--delete-existing-sources",
        action="store_true",
        help="Delete existing points for the indexed source names before upsert.",
    )
    return parser


# Điều phối toàn bộ pipeline ingestion:
# load file knowledge -> chunk -> embedding -> upsert vào Qdrant runtime collection.
def main() -> None:
    # Load .env để script dùng cùng Qdrant host/port/collection với chatbot runtime.
    load_dotenv(BACKEND_ROOT / ".env")
    args = _build_parser().parse_args()

    knowledge_dir = Path(args.knowledge_dir)
    # RAGConfig giữ các tham số chunk/embedding/vector size, còn collection lấy từ .env runtime.
    config = RAGConfig(
        embedding_model_name=os.getenv(
            "EMBED_MODEL_NAME",
            "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        ),
        collection_name=os.getenv("QDRANT_COLLECTION", "kb_chunks"),
    )
    # Kết nối Qdrant server thay vì dùng local path mặc định để chatbot retrieve thấy dữ liệu mới.
    client = QdrantClient(
        host=os.getenv("QDRANT_HOST", "localhost"),
        port=_env_int("QDRANT_PORT", 6333),
        api_key=os.getenv("QDRANT_API_KEY") or None,
    )
    try:
        # Reuse các component RAG sẵn có, script chỉ wire dependency và không tự implement parser.
        indexer = KnowledgeIndexer(
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
                client=client,
                collection_name=config.collection_name,
                vector_size=config.vector_size,
            ),
            config=config,
        )
        # Mặc định không recreate collection để tránh xóa nhầm dữ liệu.
        # Khi cần rebuild sạch, người vận hành phải truyền --recreate rõ ràng.
        indexed_count = indexer.index_directory(
            knowledge_dir,
            recreate_collection=args.recreate,
            delete_existing_sources=args.delete_existing_sources
            or _env_bool("RAG_DELETE_EXISTING_SOURCES_ON_INDEX"),
        )
    finally:
        # Đóng client để giải phóng connection/file lock sau khi index xong.
        client.close()

    print(
        f"Indexed {indexed_count} chunks from {knowledge_dir} "
        f"into Qdrant collection '{config.collection_name}'."
    )


if __name__ == "__main__":
    main()
