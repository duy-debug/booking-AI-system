# Shared dependencies — get_db + helpers

from collections.abc import Generator
from uuid import UUID

# Depends, Path được import trong các router file
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.db.session import SessionLocal


# Tạo database session cho từng request và luôn đóng kết nối sau khi handler hoàn tất.
def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Chuyển chuỗi sang UUID; nếu sai định dạng thì trả AppError 400 gắn với đúng tên trường.
def parse_uuid(value: str, field_name: str = "id") -> UUID:
    try:
        return UUID(value)
    except ValueError:
        raise AppError(
            status_code=400,
            code=f"INVALID_{field_name.upper()}_ID",
            detail=f"{field_name} không đúng format UUID",
        )
