from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ConversationStep(StrEnum):
    IDLE = "idle"
    COLLECT_SHOP = "collect_shop"
    COLLECT_SERVICE = "collect_service"
    COLLECT_ADDONS = "collect_addons"
    COLLECT_PEOPLE = "collect_people"
    COLLECT_DATE = "collect_date"
    COLLECT_TIME = "collect_time"
    COLLECT_THERAPIST_REQUEST = "collect_therapist_request"
    CHECK_AVAILABILITY = "check_availability"
    COLLECT_CUSTOMER = "collect_customer"
    AWAIT_CONFIRMATION = "await_confirmation"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass(slots=True)
class ConversationState:
    conversation_id: str
    intent: str | None = None
    step: ConversationStep = ConversationStep.IDLE
    entities: dict[str, Any] = field(default_factory=dict)
    version: int = 0

    # Hợp nhất entity mới nhưng bỏ qua giá trị rỗng để không ghi đè dữ liệu hợp lệ.
    def merge_entities(self, entities: dict[str, Any]) -> None:
        for key, value in entities.items():
            if value is not None and value != "":
                self.entities[key] = value

    # Chuyển state thuần Python thành dictionary có thể lưu trong Redis.
    def to_dict(self) -> dict[str, Any]:
        return {
            "conversation_id": self.conversation_id,
            "intent": self.intent,
            "step": self.step.value,
            "entities": self.entities,
            "version": self.version,
        }

    # Khôi phục state từ Redis và dùng giá trị mặc định cho dữ liệu phiên bản cũ.
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConversationState":
        return cls(
            conversation_id=str(data["conversation_id"]),
            intent=data.get("intent"),
            step=ConversationStep(data.get("step", ConversationStep.IDLE.value)),
            entities=dict(data.get("entities") or {}),
            version=int(data.get("version", 0)),
        )
