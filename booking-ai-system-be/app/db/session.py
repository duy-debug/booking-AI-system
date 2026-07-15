# Cấu hình kết nối database Supabase PostgreSQL và tạo session
# Đọc DATABASE_URL từ file .env (tuyệt đối không hardcode)

from collections.abc import Generator
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# Load biến môi trường từ file .env
load_dotenv()

# Lấy connection string từ biến môi trường (không hardcode vào code)
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL chưa được cấu hình trong file .env")


# Engine kết nối pool
# pool_pre_ping=true: kiểm tra kết nối còn sống trước khi dùng
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

# Factory tạo session
# expire_on_commit=false: object không bị expire sau commit
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)


# Dependency cho FastAPI — inject DB session vào router
def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()