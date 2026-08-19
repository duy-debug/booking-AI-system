"""Embedding sentence-transformer local, lazy-load cho knowledge retrieval."""

from collections.abc import Callable, Sequence
from importlib import import_module
from math import isfinite
from threading import Lock
from typing import Protocol, cast


class _SentenceEncoder(Protocol):
    def encode(
        self,
        sentences: Sequence[str],
        *,
        normalize_embeddings: bool,
    ) -> object: ...

    def get_sentence_embedding_dimension(self) -> int | None: ...


EncoderLoader = Callable[[str], _SentenceEncoder]


class SentenceTransformerEmbedding:
    """Embed query và document bằng một local model được lazy-load."""

    def __init__(
        self,
        model_name: str,
        *,
        model_loader: EncoderLoader | None = None,
    ) -> None:
        normalized_model_name = model_name.strip()
        if not normalized_model_name:
            raise ValueError("Embedding model name must not be empty.")
        self._model_name = normalized_model_name
        self._model_loader = model_loader or _load_sentence_transformer
        self._model: _SentenceEncoder | None = None
        self._dimension: int | None = None
        self._load_lock = Lock()

    @property
    def dimension(self) -> int:
        """Trả vector dimension sau lần embed đầu tiên."""
        if self._dimension is None:
            raise RuntimeError("Embedding dimension is available after the model has encoded text.")
        return self._dimension

    @property
    def model_name(self) -> str:
        """Trả tên sentence-transformer model đang cấu hình."""
        return self._model_name

    def embed_query(self, text: str) -> list[float]:
        """Trả một semantic vector đã normalize cho query không rỗng."""
        # ----------------------------------------------------
        # STEP 1: Kiểm tra text query
        # ----------------------------------------------------
        #
        # Query rỗng không có ý nghĩa để embed và cũng dễ tạo kết quả
        # retrieval nhiễu.
        # ----------------------------------------------------
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Embedding query must not be empty.")

        # ----------------------------------------------------
        # STEP 2: Encode một query thành một vector
        # ----------------------------------------------------
        #
        # _encode() luôn trả list vector theo thứ tự input, nên query đầu
        # vào một phần tử sẽ lấy vector ở index 0.
        # ----------------------------------------------------
        return self._encode((text,))[0]

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """Batch encode document theo đúng thứ tự input."""
        # ----------------------------------------------------
        # STEP 1: Chuẩn hóa input thành tuple
        # ----------------------------------------------------
        #
        # Tuple giúp giữ snapshot ổn định nếu caller truyền generator hoặc
        # sequence có thể thay đổi trong lúc encode.
        # ----------------------------------------------------
        document_texts = tuple(texts)
        if not document_texts:
            return []

        # ----------------------------------------------------
        # STEP 2: Kiểm tra từng document text
        # ----------------------------------------------------
        #
        # Mỗi chunk/document phải có nội dung thật trước khi gửi vào model.
        # ----------------------------------------------------
        if any(not isinstance(text, str) or not text.strip() for text in document_texts):
            raise ValueError("Embedding documents must contain non-empty text.")

        # ----------------------------------------------------
        # STEP 3: Encode document theo batch
        # ----------------------------------------------------
        #
        # Batch encode nhanh hơn encode từng chunk riêng lẻ và vẫn giữ đúng
        # thứ tự vector theo thứ tự text đầu vào.
        # ----------------------------------------------------
        return self._encode(document_texts)

    def _encode(self, texts: Sequence[str]) -> list[list[float]]:
        # ----------------------------------------------------
        # STEP 1: Đọc model sentence-transformer khi thật sự cần
        # ----------------------------------------------------
        #
        # Model chỉ được load khi có request embed đầu tiên để startup app
        # nhẹ hơn và test dễ mock hơn.
        # ----------------------------------------------------
        model = self._get_model()

        # ----------------------------------------------------
        # STEP 2: Encode text thành normalized vector
        # ----------------------------------------------------
        #
        # normalize_embeddings=True giúp cosine similarity ổn định hơn khi
        # Qdrant dùng cosine distance.
        # ----------------------------------------------------
        raw_vectors = model.encode(
            texts,
            normalize_embeddings=True,
        )

        # ----------------------------------------------------
        # STEP 3: Chuẩn hóa output của model
        # ----------------------------------------------------
        #
        # SentenceTransformer có thể trả numpy array hoặc kiểu tương tự,
        # nên cần ép về list[list[float]] để phần còn lại không phụ thuộc numpy.
        # ----------------------------------------------------
        vectors = _coerce_vectors(raw_vectors)
        if len(vectors) != len(texts):
            raise ValueError("Embedding model returned an unexpected vector count.")

        # ----------------------------------------------------
        # STEP 4: Kiểm tra dimension của vector
        # ----------------------------------------------------
        #
        # Dimension phải nhất quán với model để writer tạo/check Qdrant
        # collection đúng schema.
        # ----------------------------------------------------
        model_dimension = model.get_sentence_embedding_dimension()
        if type(model_dimension) is not int or model_dimension <= 0:
            raise ValueError("Embedding model returned an invalid vector dimension.")
        if any(len(vector) != model_dimension for vector in vectors):
            raise ValueError("Embedding model returned inconsistent vector dimensions.")
        self._dimension = model_dimension
        return vectors

    def _get_model(self) -> _SentenceEncoder:
        # ----------------------------------------------------
        # STEP 1: Tái sử dụng model đã load
        # ----------------------------------------------------
        #
        # SentenceTransformer khá nặng, nên mỗi instance chỉ load một lần.
        # ----------------------------------------------------
        model = self._model
        if model is not None:
            return model

        # ----------------------------------------------------
        # STEP 2: Lock khi lazy-load model
        # ----------------------------------------------------
        #
        # Lock tránh hai request đồng thời cùng load model hai lần.
        # ----------------------------------------------------
        with self._load_lock:
            model = self._model
            if model is None:
                model = self._model_loader(self._model_name)
                self._model = model
        return model


def _load_sentence_transformer(model_name: str) -> _SentenceEncoder:
    """Load sentence-transformer model đã cấu hình khi thật sự cần."""
    # ----------------------------------------------------
    # STEP 1: Import sentence_transformers khi thật sự cần
    # ----------------------------------------------------
    #
    # Dependency này nặng, nên import lazy để app/test không phải load nó
    # nếu chưa chạy RAG embedding.
    # ----------------------------------------------------
    sentence_transformers_module = import_module("sentence_transformers")
    sentence_transformer = getattr(sentence_transformers_module, "SentenceTransformer")
    return cast(
        _SentenceEncoder,
        sentence_transformer(model_name, local_files_only=True),
    )


def _coerce_vectors(raw_vectors: object) -> list[list[float]]:
    """Coerce embedding output into a valid 2D float vector collection."""
    # ----------------------------------------------------
    # STEP 1: Đưa output về Python sequence
    # ----------------------------------------------------
    #
    # Nếu model trả numpy array, tolist() sẽ biến nó thành list thuần.
    # ----------------------------------------------------
    converter = getattr(raw_vectors, "tolist", None)
    converted = converter() if callable(converter) else raw_vectors
    if not isinstance(converted, Sequence) or isinstance(converted, str | bytes):
        raise ValueError("Embedding model returned an invalid vector collection.")

    # ----------------------------------------------------
    # STEP 2: Kiểm tra từng vector và từng giá trị float
    # ----------------------------------------------------
    #
    # Vector phải là số hữu hạn; NaN/Infinity sẽ làm Qdrant similarity
    # không đáng tin cậy.
    # ----------------------------------------------------
    vectors: list[list[float]] = []
    for raw_vector in converted:
        if not isinstance(raw_vector, Sequence) or isinstance(raw_vector, str | bytes):
            raise ValueError("Embedding model returned an invalid vector.")
        vector = [float(value) for value in raw_vector]
        if not all(isfinite(value) for value in vector):
            raise ValueError("Embedding model returned a non-finite vector value.")
        vectors.append(vector)
    return vectors
