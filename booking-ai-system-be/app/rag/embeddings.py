# Local embedding với sentence-transformers (all-MiniLM-L6-v2, 384 dim)
# Chạy hoàn toàn local, không gọi API bên ngoài

from functools import lru_cache

from sentence_transformers import SentenceTransformer

from app.core.config import settings


@lru_cache(maxsize=1)
def get_embedding_model() -> SentenceTransformer:
    # Singleton model — load 1 lần, giữ trong memory
    return SentenceTransformer(settings.EMBED_MODEL_NAME)


def embed_text(text: str) -> list[float]:
    # Nhúng một đoạn text → list[float] 384 chiều
    model = get_embedding_model()
    return model.encode(text, normalize_embeddings=True).tolist()


def embed_texts(texts: list[str]) -> list[list[float]]:
    # Nhúng batch nhiều text cùng lúc (nhanh hơn gọi từng cái)
    model = get_embedding_model()
    return model.encode(texts, normalize_embeddings=True).tolist()
