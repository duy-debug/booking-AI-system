"""Khai báo schema HTTP dùng chung cho hai nhánh JSON và SSE của chatbot."""

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# Schema public cho message đầu vào; validator ở đây bảo vệ transport trước khi vào dialog.
class ChatRequest(BaseModel):
    """Chứa một message người dùng cùng conversation identity do transport quản lý."""

    model_config = ConfigDict(extra="forbid")

    conversation_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=2000)
    idempotency_key: str | None = None

    @field_validator("conversation_id", mode="before")
    @classmethod
    # Chuẩn hóa conversation id để store không nhận key rỗng hoặc lệch do khoảng trắng.
    def normalize_conversation_id(cls, value: object) -> object:
        """Chuẩn hóa khoảng trắng đầu cuối và để tầng store kiểm tra contract cuối cùng."""
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        if not normalized:
            raise ValueError("conversation_id must not be empty")
        return normalized

    @field_validator("message", mode="before")
    @classmethod
    # Chỉ trim hai đầu message, giữ nguyên nội dung giữa câu để NLU không mất tín hiệu.
    def normalize_message(cls, value: object) -> object:
        """Chỉ cắt khoảng trắng đầu cuối của message mà không đổi nội dung bên trong."""
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        if not normalized:
            raise ValueError("message must not be empty")
        return normalized

    @model_validator(mode="after")
    # Idempotency key rỗng phải bị từ chối để create/cancel booking không bị dedupe sai.
    def reject_empty_idempotency_key(self) -> Self:
        """Từ chối idempotency key rỗng nếu client truyền vào một cách tường minh."""
        if self.idempotency_key == "":
            raise ValueError("idempotency_key must not be empty")
        return self


# Schema response public giữ contract ổn định cho cả endpoint JSON và SSE final event.
class ChatResponse(BaseModel):
    """Chứa dữ liệu phản hồi an toàn để frontend hiển thị cho một lượt chat JSON."""

    conversation_id: str
    text: str
    state: str
    status: str
    instruction_template: str | None
    metadata: dict[str, bool | int | float | str | None]
