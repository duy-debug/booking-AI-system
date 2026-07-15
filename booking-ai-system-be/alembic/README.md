# Alembic Migrations — Booking AI System

## Cấu trúc

```
alembic/
├── env.py              # Cấu hình kết nối và metadata
├── script.py.mako      # Template cho migration files
├── README.md
└── versions/           # Chứa các file migration
    └── dee2e56ef8bf_create_initial_booking_schema.py
```

## Các lệnh thường dùng

```bash
# Tạo migration mới (so sánh models với database)
alembic revision --autogenerate -m "mo ta thay doi"

# Apply migration lên database
alembic upgrade head

# Rollback 1 bước
alembic downgrade -1

# Xem trạng thái hiện tại
alembic current

# Kiểm tra models có đồng bộ với database không
alembic check

# Xem lịch sử migration
alembic history
```

## Lưu ý

- **Không hardcode** `DATABASE_URL` — đọc từ file `.env`
- Sau khi sửa models, chạy `alembic revision --autogenerate` để tạo migration
- Review file migration trước khi chạy `upgrade head`
- File migration không được sửa sau khi đã commit và apply
