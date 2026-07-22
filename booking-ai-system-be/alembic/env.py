# Cấu hình Alembic — đọc models và kết nối Supabase
# Chạy: alembic revision --autogenerate -m "..."  và  alembic upgrade head

import os
from logging.config import fileConfig

from dotenv import load_dotenv
from sqlalchemy import create_engine, pool

from alembic import context

# Load biến môi trường từ file .env
load_dotenv()

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import toàn bộ models để Alembic đọc được metadata
from app.db.base import Base
from app.db.models import *

target_metadata = Base.metadata

# Đọc DATABASE_URL từ .env (không hardcode)
DATABASE_URL = os.getenv("DATABASE_URL")


# Cấu hình migration offline bằng URL và literal bind để sinh SQL mà không mở kết nối database.
def run_migrations_offline() -> None:
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


# Mở kết nối database không dùng pool và chạy migration online trong một transaction Alembic.
def run_migrations_online() -> None:
    connectable = create_engine(DATABASE_URL, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
