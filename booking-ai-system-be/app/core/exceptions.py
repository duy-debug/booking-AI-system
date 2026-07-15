# AppError — RFC 9457 Problem Details cho toàn bộ API
# Dùng thay cho HTTPException để đảm bảo error format đồng nhất

from fastapi import HTTPException


class AppError(HTTPException):
    # Lỗi ứng dụng — tự động format theo RFC 9457 Problem Details

    def __init__(
        self,
        status_code: int,
        code: str,
        detail: str = "",
        instance: str | None = None,
        errors: list[dict] | None = None,
        headers: dict[str, str] | None = None,
    ):
        body = {
            "type": "about:blank",
            "title": code.replace("_", " ").title(),
            "status": status_code,
            "detail": detail,
            "code": code,
        }
        if instance:
            body["instance"] = instance
        if errors:
            body["errors"] = errors
        super().__init__(status_code=status_code, detail=body, headers=headers)
