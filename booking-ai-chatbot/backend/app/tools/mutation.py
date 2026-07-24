from __future__ import annotations

from typing import Any

from app.application.booking_workflow import BookingWorkflow
from app.domain.models import PendingAction
from app.policies.tool_policy import ensure_public_tool


class MutationTools:
    # Nhận BookingWorkflow để tool không trực tiếp gọi HTTP adapter.
    def __init__(self, workflow: BookingWorkflow) -> None:
        self._workflow = workflow

    # Chuẩn bị mutation và trả token; chưa ghi dữ liệu vào Booking Backend.
    async def prepare(
        self,
        conversation_id: str,
        action: str,
        payload: dict[str, Any],
    ) -> PendingAction:
        tool_name = {
            "create_booking": "create_booking",
            "update_booking": "update_booking",
            "cancel_booking": "cancel_booking",
        }.get(action, action)
        ensure_public_tool(tool_name)
        return await self._workflow.prepare(conversation_id, action, payload)

    # Thực thi mutation đã đóng băng payload sau khi confirmation token hợp lệ.
    async def confirm(self, conversation_id: str, confirmation_token: str) -> dict[str, Any]:
        return await self._workflow.confirm(conversation_id, confirmation_token)
