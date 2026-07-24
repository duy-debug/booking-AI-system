from __future__ import annotations

from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


class ChatSelection(BaseModel):
    entity: str = Field(..., min_length=1, max_length=64)
    value: Any
    label: str | None = Field(None, max_length=200)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatRequest(BaseModel):
    query: str | None = Field(None, min_length=1, max_length=2000)
    conversation_id: str = Field(default_factory=lambda: str(uuid4()))
    selection: ChatSelection | None = None

    # Bắt buộc request phải có câu nói hoặc một lựa chọn có cấu trúc từ giao diện.
    @model_validator(mode="after")
    def validate_interaction(self) -> "ChatRequest":
        if self.query is None and self.selection is None:
            raise ValueError("query hoặc selection là bắt buộc")
        return self


class UIOption(BaseModel):
    id: str
    label: str
    description: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class UIBlock(BaseModel):
    type: Literal[
        "text",
        "shop_options",
        "course_options",
        "addon_options",
        "people_options",
        "date_picker",
        "slot_options",
        "therapist_request_options",
        "therapist_options",
        "gender_options",
        "customer_form",
        "booking_summary",
        "confirmation",
        "booking_result",
    ]
    options: list[UIOption] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    answer: str
    intent: str
    conversation_id: str | None = None
    data: Any | None = None
    missing_entities: list[str] | None = None
    ui: UIBlock | None = None


class HealthResponse(BaseModel):
    status: str


class ApplicationInfoResponse(BaseModel):
    message: str
