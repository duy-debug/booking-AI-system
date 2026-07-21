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

    # Auth — Supabase Auth JWT verification (asymmetric / JWKS)
    SUPABASE_JWKS_URL: str  # URL JWKS của project Supabase (verify token ECC/RS256)
    JWT_ALGORITHM: str = "ES256"  # Supabase mặc định ký bằng ECC P-256
    ADMIN_EMAILS: list[str] = []  # Whitelist email được phép vào /api/admin/*

    # CORS — cho phép FE local dev
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    # Supabase test account (chỉ dùng cho integration tests — conftest.py)
    SUPABASE_TEST_EMAIL: str | None = None
    SUPABASE_TEST_PASSWORD: str | None = None

    # Múi giờ nghiệp vụ mặc định của shop. Backend lưu start_time/end_time là
    # giá trị NAIVE (không kèm múi giờ); client phải interpret theo múi giờ này.
    SHOP_TIMEZONE: str = "Asia/Ho_Chi_Minh"

    # Khung giờ hoạt động mặc định dùng khi shop không có ca nào trong ngày.
    BUSINESS_HOURS_OPEN: str = "09:00"
    BUSINESS_HOURS_CLOSE: str = "22:00"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
