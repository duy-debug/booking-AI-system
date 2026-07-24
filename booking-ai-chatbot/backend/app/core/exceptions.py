from typing import Any


class AppError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        detail: str,
        *,
        errors: list[dict[str, Any]] | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.detail = {
            "type": "about:blank",
            "title": code.replace("_", " ").title(),
            "status": status_code,
            "detail": detail,
            "code": code,
        }
        if errors:
            self.detail["errors"] = errors
        super().__init__(detail)
