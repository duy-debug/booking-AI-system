from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any


@dataclass(slots=True)
class PendingAction:
    conversation_id: str
    action: str
    payload: dict[str, Any]
    confirmation_token: str = field(default_factory=lambda: secrets.token_hex(6).upper())
    expires_at: datetime = field(default_factory=lambda: datetime.now(UTC) + timedelta(minutes=10))

    # Kiểm tra thao tác chờ còn hiệu lực trước khi cho phép thực thi mutation.
    def is_expired(self) -> bool:
        return datetime.now(UTC) >= self.expires_at
