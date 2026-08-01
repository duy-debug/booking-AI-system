"""Validated HTTP schemas for the non-streaming chat transport."""

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ChatRequest(BaseModel):
    """Contains one user message and its transport-owned conversation identity."""

    model_config = ConfigDict(extra="forbid")

    conversation_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=2000)
    idempotency_key: str | None = None

    @field_validator("conversation_id", mode="before")
    @classmethod
    def normalize_conversation_id(cls, value: object) -> object:
        """Trim the identifier while leaving authoritative checks to the store."""
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        if not normalized:
            raise ValueError("conversation_id must not be empty")
        return normalized

    @field_validator("message", mode="before")
    @classmethod
    def normalize_message(cls, value: object) -> object:
        """Trim only outer message whitespace without changing its content."""
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        if not normalized:
            raise ValueError("message must not be empty")
        return normalized

    @model_validator(mode="after")
    def reject_empty_idempotency_key(self) -> Self:
        """Reject an explicitly empty key without normalizing supplied values."""
        if self.idempotency_key == "":
            raise ValueError("idempotency_key must not be empty")
        return self


class ChatResponse(BaseModel):
    """Contains UI-safe output from one non-streaming dialog turn."""

    conversation_id: str
    text: str
    state: str
    status: str
    instruction_template: str | None
    quick_replies: list[str]
    metadata: dict[str, bool | int | float | str | None]
