from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.domain.intent import Intent


@dataclass(slots=True)
class NLUResult:
    intent: Intent
    resource: str | None = None
    operation: str | None = None
    entities: dict[str, Any] = field(default_factory=dict)

    # Chuyển kết quả domain thành dữ liệu JSON an toàn cho API và logging.
    def to_dict(self) -> dict[str, Any]:
        return {
            "intent": self.intent.value,
            "resource": self.resource,
            "operation": self.operation,
            "entities": self.entities,
        }
