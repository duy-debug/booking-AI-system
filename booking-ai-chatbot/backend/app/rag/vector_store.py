
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    PointStruct,
    VectorParams,
)

from app.rag.chunker import Chunk


# ============================================================
# VectorStore
# ============================================================
#
# Class này chịu trách nhiệm duy nhất:
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
#
# Nó KHÔNG:
#
# - đọc file
# - chunk document
# - tạo embedding
# - gọi LLM
#
#
# Pipeline:
#
# Chunk
#   +
# Vector
#   ↓
# Point
#   ↓
# Qdrant
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
            tên collection dùng để chứa knowledge.

        vector_size:
            dimension của embedding vector.

            Với:
            sentence-transformers/all-MiniLM-L6-v2

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
        # 4. Khởi tạo Qdrant client
        # ----------------------------------------------------
        #
        # Local mode:
        #
        # Qdrant sẽ lưu dữ liệu tại:
        #
        # qdrant_data/
        #
        # Không cần chạy Docker/server riêng.
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

        Collection sẽ được cấu hình:

        vector size:
            384

        distance:
            cosine
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
        # 2. chunks và vectors phải bằng nhau
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
        # 4. Ghép Chunk với Vector
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
            # Qdrant Point gồm:
            #
            # id
            # vector
            # payload
            #
            # payload là metadata ta muốn lấy lại
            # khi search.
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


            points.append(
                point
            )


        # ----------------------------------------------------
        # 5. Lưu vào Qdrant
        # ----------------------------------------------------

        self.client.upsert(
            collection_name=self.collection_name,
            points=points,
        )


    # ========================================================
    # Count
    # ========================================================

    def count(
        self,
    ) -> int:
        """
        Đếm số Point hiện có trong collection.

        Chủ yếu hữu ích để test/debug.
        """

        result = self.client.count(
            collection_name=self.collection_name,
            exact=True,
        )

        return result.count