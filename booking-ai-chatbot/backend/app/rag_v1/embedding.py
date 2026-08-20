from importlib import import_module

from app.rag_v1.chunker import Chunk

# ============================================================
# EmbeddingModel
# ============================================================
#
# Class này chịu trách nhiệm duy nhất:
#
# text / Chunk
#      ↓
# embedding model
#      ↓
# vector
#
# Nó KHÔNG làm:
#
# - đọc file
# - chunk document
# - lưu Qdrant
# - retrieval
# - gọi LLM
#
# Ví dụ:
#
# "Khách hàng có thể hủy lịch trước 24 giờ."
#
#           ↓
#
# EmbeddingModel
#
#           ↓
#
# [
#     0.021,
#     -0.143,
#     0.512,
#     ...
# ]
#
# ============================================================

class EmbeddingModel:

    def __init__(
        self,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        normalize_embeddings: bool = True,
    ) -> None:
        """
        Khởi tạo embedding model.

        model_name:
            Tên model Sentence Transformers.

        normalize_embeddings:
            Nếu True, vector sẽ được normalize.

            Điều này thường hữu ích khi dùng
            cosine similarity trong vector database.
        """

        # ----------------------------------------------------
        # 1. Validate model_name
        # ----------------------------------------------------

        if not model_name.strip():
            raise ValueError(
                "model_name cannot be empty"
            )


        # ----------------------------------------------------
        # 2. Lưu config
        # ----------------------------------------------------

        self.model_name = model_name

        self.normalize_embeddings = (
            normalize_embeddings
        )


        # ----------------------------------------------------
        # 3. Load embedding model
        # ----------------------------------------------------
        #
        # Model sẽ được load một lần khi tạo EmbeddingModel.
        #
        # Không nên load model lại mỗi lần gọi embed_text(),
        # vì rất tốn thời gian.
        # ----------------------------------------------------

        sentence_transformers_module = import_module("sentence_transformers")
        sentence_transformer = sentence_transformers_module.SentenceTransformer
        self.model = sentence_transformer(
            model_name
        )


    def embed_text(
        self,
        text: str,
    ) -> list[float]:
        """
        Biến một đoạn text thành embedding vector.

        Flow:

        text
          ↓
        model.encode()
          ↓
        numpy array
          ↓
        list[float]
        """

        # ----------------------------------------------------
        # 1. Validate text
        # ----------------------------------------------------

        if not text.strip():
            raise ValueError(
                "Text for embedding cannot be empty"
            )


        # ----------------------------------------------------
        # 2. Encode text
        # ----------------------------------------------------

        vector = self.model.encode(
            text,
            normalize_embeddings=self.normalize_embeddings,
        )


        # ----------------------------------------------------
        # 3. Chuyển numpy array → Python list
        # ----------------------------------------------------

        return vector.tolist()


    def embed_chunk(
        self,
        chunk: Chunk,
    ) -> list[float]:
        """
        Embed một Chunk.

        Chunk
          ↓
        chunk.text
          ↓
        embed_text()
          ↓
        vector
        """

        return self.embed_text(
            chunk.text
        )


    def embed_chunks(
        self,
        chunks: list[Chunk],
    ) -> list[list[float]]:
        """
        Embed nhiều Chunk cùng lúc.

        Flow:

        list[Chunk]
             ↓
        lấy chunk.text
             ↓
        list[str]
             ↓
        model.encode(batch)
             ↓
        list[list[float]]

        Batch embedding thường nhanh hơn việc encode
        từng chunk riêng lẻ.
        """

        # ----------------------------------------------------
        # 1. Không có chunk
        # ----------------------------------------------------

        if not chunks:
            return []


        # ----------------------------------------------------
        # 2. Lấy text từ tất cả Chunk
        # ----------------------------------------------------

        texts = [
            chunk.text
            for chunk in chunks
        ]


        # ----------------------------------------------------
        # 3. Batch embedding
        # ----------------------------------------------------

        vectors = self.model.encode(
            texts,
            normalize_embeddings=self.normalize_embeddings,
        )


        # ----------------------------------------------------
        # 4. numpy ndarray → Python list
        # ----------------------------------------------------

        return vectors.tolist()
