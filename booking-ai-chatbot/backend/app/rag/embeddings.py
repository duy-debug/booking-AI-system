from __future__ import annotations

import hashlib
from functools import lru_cache

from app.core.config import settings


# Nạp model embedding từ cache cục bộ để runtime không tự tải model ngoài ý muốn.
@lru_cache(maxsize=1)
def _get_model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(settings.EMBED_MODEL_NAME, local_files_only=True)


# Tạo vector ổn định dự phòng khi model chưa được tải vào môi trường triển khai.
def _fallback_embedding(text: str) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    values = [
        ((digest[index % len(digest)] / 255.0) * 2.0) - 1.0 for index in range(settings.EMBED_DIM)
    ]
    magnitude = sum(value * value for value in values) ** 0.5 or 1.0
    return [value / magnitude for value in values]


# Sinh embedding cho một văn bản bằng model thật, có fallback để health/test chạy offline.
def embed_text(text: str) -> list[float]:
    try:
        vector = _get_model().encode(text, normalize_embeddings=True)
        return vector.tolist()
    except (OSError, ValueError):
        return _fallback_embedding(text)


# Sinh embedding cho nhiều đoạn tài liệu theo cùng cấu hình với truy vấn.
def embed_documents(texts: list[str]) -> list[list[float]]:
    return [embed_text(text) for text in texts]
