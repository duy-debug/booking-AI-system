# Shared dependencies — get_db + helpers

from collections.abc import Generator
from uuid import UUID

# Depends, Path được import trong các router file
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.db.session import SessionLocal


def get_db() -> Generator[Session, None, None]:
    # Inject DB session vào router handler
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def parse_uuid(value: str, field_name: str = "id") -> UUID:
    # Parse UUID string, raise 400 nếu không hợp lệ
    try:
        return UUID(value)
    except ValueError:
        raise AppError(
            status_code=400,
            code=f"INVALID_{field_name.upper()}_ID",
            detail=f"{field_name} không đúng format UUID",
        )
