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

    # Auth — Supabase Auth JWT verification (asymmetric / JWKS)
    SUPABASE_JWKS_URL: str  # URL JWKS của project Supabase (verify token ECC/RS256)
    JWT_ALGORITHM: str = "ES256"  # Supabase mặc định ký bằng ECC P-256
    JWT_CLOCK_SKEW_SECONDS: int = 30  # Dung sai lệch đồng hồ giữa Supabase và backend khi kiểm tra iat/nbf/exp
    ADMIN_EMAILS: list[str] = []  # Whitelist email được phép vào /api/admin/*

    # CORS — cho phép FE local dev
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    # Supabase test account (chỉ dùng cho integration tests — conftest.py)
    SUPABASE_TEST_EMAIL: str | None = None
    SUPABASE_TEST_PASSWORD: str | None = None

    # Múi giờ nghiệp vụ mặc định của shop. Backend lưu start_time/end_time là
    # giá trị NAIVE (không kèm múi giờ); client phải interpret theo múi giờ này.
    SHOP_TIMEZONE: str = "Asia/Ho_Chi_Minh"
    MINIMUM_BOOKING_ADVANCE_MINUTES: int = 15

    # Structured logging
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "console"
    LOG_USER_MESSAGES: bool = False
    LOG_AI_MESSAGES: bool = False
    LOG_LLM_PROMPTS: bool = False
    LOG_LLM_RAW_RESPONSE: bool = False
    LOG_POS_PAYLOADS: bool = False
    LOG_QDRANT_CONTENT: bool = False
    LOG_DATABASE_QUERIES: bool = False

    # Khung giờ hoạt động mặc định dùng khi shop không có ca nào trong ngày.
    BUSINESS_HOURS_OPEN: str = "09:00"
    BUSINESS_HOURS_CLOSE: str = "22:00"

    # Bỏ qua biến legacy trong .env để deployment cũ vẫn khởi động được sau khi
    # các cấu hình AI được chuyển hoàn toàn sang Chatbot service.
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()
