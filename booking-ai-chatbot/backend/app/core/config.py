from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    APP_NAME: str = "Booking AI Chatbot"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = Field(False, validation_alias="CHATBOT_DEBUG")
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
    EMBED_MODEL_NAME: str = "all-MiniLM-L6-v2"
    EMBED_DIM: int = 384
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_COLLECTION: str = "kb_chunks"
    BOOKING_API_URL: str = "http://localhost:8000"
    BOOKING_API_SERVICE_KEY: str = ""
    BOOKING_API_TIMEOUT_SECONDS: float = 10.0
    REDIS_URL: str = "redis://localhost:6379/0"
    CONVERSATION_TTL_SECONDS: int = 1800
    BUSINESS_TIMEZONE: str = "Asia/Tokyo"
    ADMIN_API_KEY: str = "change-me-in-production"
    CORS_ORIGINS: str = "http://localhost:3000"

    # Chuyển chuỗi origin từ biến môi trường thành danh sách dùng cho CORS middleware.
    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


# Cache cấu hình để toàn ứng dụng dùng chung một instance nhất quán.
@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
