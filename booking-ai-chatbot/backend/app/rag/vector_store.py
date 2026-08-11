from dataclasses import dataclass

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    PointStruct,
    VectorParams,
)

from app.rag.chunker import Chunk


# ============================================================
# SearchResult
# ============================================================
#
# Đây là cấu trúc dữ liệu đại diện cho MỘT kết quả
# được trả về sau khi search trong Qdrant.
#
# Ví dụ:
#
# SearchResult(
#     text="RAG là phương pháp...",
#     source="rag.pdf",
#     file_path="knowledge/rag.pdf",
#     chunk_index=12,
#     score=0.82,
# )
#
# score:
#     độ tương đồng giữa query vector
#     và vector của chunk trong Qdrant.
#
# ============================================================

@dataclass
class SearchResult:
    text: str
    source: str
    file_path: str
    chunk_index: int
    score: float


# ============================================================
# VectorStore
# ============================================================
#
# Class này chịu trách nhiệm:
#
# vector + metadata
#        ↓
#      Qdrant
#
# Nó chịu trách nhiệm:
#
# - kết nối Qdrant
# - tạo collection
# - lưu vectors
# - lưu payload
# - search vectors
#
# Nó KHÔNG:
#
# - đọc file
# - chunk document
# - tạo embedding
# - gọi LLM
#
# ============================================================

class VectorStore:

    def __init__(
        self,
        path: str = "qdrant_data",
        collection_name: str = "knowledge",
        vector_size: int = 384,
    ) -> None:
        """
        Khởi tạo VectorStore.

        path:
            folder Qdrant local lưu database.

        collection_name:
            tên collection chứa knowledge.

        vector_size:
            dimension của embedding vector.

            Với all-MiniLM-L6-v2:
            vector_size = 384
        """

        # ----------------------------------------------------
        # 1. Validate collection name
        # ----------------------------------------------------

        if not collection_name.strip():
            raise ValueError(
                "collection_name cannot be empty"
            )


        # ----------------------------------------------------
        # 2. Validate vector size
        # ----------------------------------------------------

        if vector_size <= 0:
            raise ValueError(
                "vector_size must be greater than 0"
            )


        # ----------------------------------------------------
        # 3. Lưu config
        # ----------------------------------------------------

        self.path = path
        self.collection_name = collection_name
        self.vector_size = vector_size


        # ----------------------------------------------------
        # 4. Khởi tạo Qdrant local client
        # ----------------------------------------------------

        self.client = QdrantClient(
            path=path
        )


    # ========================================================
    # Create collection
    # ========================================================

    def create_collection(
        self,
    ) -> None:
        """
        Tạo collection nếu collection chưa tồn tại.
        """

        # ----------------------------------------------------
        # 1. Nếu collection đã tồn tại
        # ----------------------------------------------------

        if self.client.collection_exists(
            self.collection_name
        ):
            return


        # ----------------------------------------------------
        # 2. Nếu chưa tồn tại → tạo mới
        # ----------------------------------------------------

        self.client.create_collection(
            collection_name=self.collection_name,

            vectors_config=VectorParams(
                size=self.vector_size,
                distance=Distance.COSINE,
            ),
        )


    # ========================================================
    # Upsert
    # ========================================================

    def upsert(
        self,
        chunks: list[Chunk],
        vectors: list[list[float]],
    ) -> None:
        """
        Lưu chunks + vectors vào Qdrant.

        Mapping:

        chunks[0] ↔ vectors[0]
        chunks[1] ↔ vectors[1]
        chunks[2] ↔ vectors[2]

        Mỗi cặp trở thành một Point trong Qdrant.
        """

        # ----------------------------------------------------
        # 1. Không có dữ liệu
        # ----------------------------------------------------

        if not chunks:
            return


        # ----------------------------------------------------
        # 2. Số chunks phải bằng số vectors
        # ----------------------------------------------------

        if len(chunks) != len(vectors):
            raise ValueError(
                "Number of chunks must match "
                "number of vectors"
            )


        # ----------------------------------------------------
        # 3. List chứa PointStruct
        # ----------------------------------------------------

        points: list[PointStruct] = []


        # ----------------------------------------------------
        # 4. Ghép Chunk ↔ Vector
        # ----------------------------------------------------

        for index, (chunk, vector) in enumerate(
            zip(chunks, vectors)
        ):

            # ------------------------------------------------
            # Validate vector dimension
            # ------------------------------------------------

            if len(vector) != self.vector_size:
                raise ValueError(
                    f"Invalid vector size: expected "
                    f"{self.vector_size}, "
                    f"got {len(vector)}"
                )


            # ------------------------------------------------
            # Tạo Point
            # ------------------------------------------------
            #
            # Một Point gồm:
            #
            # id
            # vector
            # payload
            # ------------------------------------------------

            point = PointStruct(
                id=index,

                vector=vector,

                payload={
                    "text": chunk.text,
                    "source": chunk.source,
                    "file_path": chunk.file_path,
                    "chunk_index": chunk.chunk_index,
                },
            )

            points.append(point)


        # ----------------------------------------------------
        # 5. Lưu vào Qdrant
        # ----------------------------------------------------

        self.client.upsert(
            collection_name=self.collection_name,
            points=points,
        )


    # ========================================================
    # Search
    # ========================================================

    def search(
        self,
        query_vector: list[float],
        limit: int = 5,
    ) -> list[SearchResult]:
        """
        Search các Point gần query vector nhất.

        Flow:

        query vector
             ↓
        Qdrant cosine similarity
             ↓
        top-k Point
             ↓
        payload + score
             ↓
        SearchResult[]
        """

        # ----------------------------------------------------
        # 1. Validate query vector dimension
        # ----------------------------------------------------

        if len(query_vector) != self.vector_size:
            raise ValueError(
                f"Invalid query vector size: expected "
                f"{self.vector_size}, "
                f"got {len(query_vector)}"
            )


        # ----------------------------------------------------
        # 2. Validate limit
        # ----------------------------------------------------

        if limit <= 0:
            raise ValueError(
                "limit must be greater than 0"
            )


        # ----------------------------------------------------
        # 3. Search trong Qdrant
        # ----------------------------------------------------
        #
        # query:
        #     embedding vector của câu hỏi.
        #
        # limit:
        #     lấy bao nhiêu Point gần nhất.
        #
        # with_payload=True:
        #     ngoài score còn lấy lại payload:
        #
        #     text
        #     source
        #     file_path
        #     chunk_index
        # ----------------------------------------------------

        response = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            limit=limit,
            with_payload=True,
        )


        # ----------------------------------------------------
        # 4. Chuyển Qdrant result → SearchResult
        # ----------------------------------------------------

        results: list[SearchResult] = []


        for point in response.points:

            # Payload có thể là None,
            # nên fallback về dictionary rỗng.
            payload = point.payload or {}


            result = SearchResult(
                text=payload.get(
                    "text",
                    "",
                ),

                source=payload.get(
                    "source",
                    "",
                ),

                file_path=payload.get(
                    "file_path",
                    "",
                ),

                chunk_index=payload.get(
                    "chunk_index",
                    -1,
                ),

                score=float(
                    point.score
                ),
            )


            results.append(result)


        # ----------------------------------------------------
        # 5. Return top-k SearchResult
        # ----------------------------------------------------

        return results


    # ========================================================
    # Count
    # ========================================================

    def count(
        self,
    ) -> int:
        """
        Đếm số Point trong collection.
        """

        result = self.client.count(
            collection_name=self.collection_name,
            exact=True,
        )

        return result.count


    # ========================================================
    # Close
    # ========================================================

    def close(
        self,
    ) -> None:
        """
        Đóng Qdrant client.

        Quan trọng khi dùng local mode trên Windows
        để giải phóng file lock đúng cách.
        """

        self.client.close()