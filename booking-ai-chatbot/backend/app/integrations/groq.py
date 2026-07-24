from functools import lru_cache

from openai import OpenAI

from app.core.config import settings
from app.core.exceptions import AppError


# Khởi tạo một OpenAI-compatible client dùng endpoint Groq và tái sử dụng connection.
@lru_cache(maxsize=1)
def get_groq_client() -> OpenAI:
    if not settings.GROQ_API_KEY:
        raise AppError(
            503,
            code="LLM_NOT_CONFIGURED",
            detail="Chưa cấu hình GROQ_API_KEY.",
        )
    return OpenAI(
        api_key=settings.GROQ_API_KEY,
        base_url=settings.GROQ_BASE_URL,
    )
