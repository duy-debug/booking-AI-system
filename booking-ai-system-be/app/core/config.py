# Cấu hình ứng dụng — đọc biến môi trường từ file .env

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    APP_NAME: str = "Booking AI System"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str

    # Supabase
    SUPABASE_URL: str
    SUPABASE_SERVICE_KEY: str
    SUPABASE_ANON_KEY: str

    # OpenAI (fallback, không bắt buộc)
    OPENAI_API_KEY: str | None = None

    # Groq — free LLM API thay thế OpenAI (tương thích OpenAI SDK)
    GROQ_API_KEY: str | None = None
    GROQ_MODEL: str = "mixtral-8x7b-32768"
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"

    # Local embedding model (sentence-transformers, 384 dim)
    EMBED_MODEL_NAME: str = "all-MiniLM-L6-v2"
    EMBED_DIM: int = 384

    # Auth / JWT
    JWT_SECRET: str = "booking-ai-system-jwt-secret-change-in-production-32chars"  # Khóa ký JWT — đổi trong .env
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 1440  # 24h
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin123"  # Đổi trong .env

    # CORS — cho phép FE local dev
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
