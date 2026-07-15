# SQLAlchemy Base class — tất cả model trong hệ thống kế thừa từ class này
# Mỗi model là một bảng trong database Supabase PostgreSQL

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
