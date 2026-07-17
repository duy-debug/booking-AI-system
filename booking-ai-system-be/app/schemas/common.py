# Schema dùng chung — pagination, error response, HATEOAS links

from __future__ import annotations

from pydantic import BaseModel


# Meta data cho danh sách có phân trang (cursor-based)
class PaginationMeta(BaseModel):

    total: int | None = None
    limit: int | None = None
    next_cursor: str | None = None


# Chi tiết lỗi theo từng field — dùng trong 422 Validation Error
class ValidationErrorDetail(BaseModel):

    field: str
    message: str


# RFC 9457 Problem Details — format lỗi chuẩn cho toàn bộ API
class ErrorResponse(BaseModel):

    type: str = "about:blank"
    title: str
    status: int
    detail: str
    code: str
    instance: str | None = None
    errors: list[ValidationErrorDetail] | None = None
