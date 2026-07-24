from __future__ import annotations

from app.core.exceptions import AppError

FORBIDDEN_REQUESTS = (
    "delete therapist",
    "xóa nhân viên",
    "danh sách khách hàng",
    "customer phone",
    "tạo nhân viên",
    "admin booking",
)


# Kiểm tra độ dài và chặn yêu cầu quản trị trước khi gửi nội dung sang LLM/router.
def guard_input(query: str) -> None:
    normalized = query.strip().lower()
    if not normalized:
        raise AppError(422, code="EMPTY_QUERY", detail="Nội dung tin nhắn không được trống.")
    if len(normalized) > 2000:
        raise AppError(
            422,
            code="QUERY_TOO_LONG",
            detail="Nội dung tin nhắn vượt quá 2.000 ký tự.",
        )
    if any(pattern in normalized for pattern in FORBIDDEN_REQUESTS):
        raise AppError(
            403,
            code="ADMIN_OPERATION_NOT_ALLOWED",
            detail="Chatbot khách hàng không được thực hiện thao tác quản trị.",
        )
