from __future__ import annotations

from typing import Any
from uuid import uuid4

from app.application.contracts import BookingGateway, ConversationStore
from app.core.exceptions import AppError
from app.domain.models import PendingAction


class BookingWorkflow:
    # Nhận gateway và state store qua abstraction để business flow dễ test độc lập.
    def __init__(
        self,
        gateway: BookingGateway,
        conversation_store: ConversationStore,
    ) -> None:
        self._gateway = gateway
        self._store = conversation_store

    # Lưu bản chụp payload mutation để câu xác nhận không thể đổi nội dung ngầm.
    async def prepare(
        self,
        conversation_id: str,
        action: str,
        payload: dict[str, Any],
    ) -> PendingAction:
        if action not in {"create_booking", "update_booking", "cancel_booking"}:
            raise AppError(
                400,
                code="UNSUPPORTED_BOOKING_ACTION",
                detail="Thao tác booking không được hỗ trợ.",
            )
        prepared = dict(payload)
        if action == "create_booking":
            prepared.setdefault("_idempotency_key", str(uuid4()))
        pending = PendingAction(
            conversation_id=conversation_id,
            action=action,
            payload=prepared,
        )
        await self._store.save_pending(pending)
        return pending

    # Xác minh token rồi thực thi đúng mutation đã lưu; chỉ xóa state sau khi API thành công.
    async def confirm(
        self,
        conversation_id: str,
        confirmation_token: str,
    ) -> dict[str, Any]:
        pending = await self._store.get_pending(conversation_id)
        if pending is None:
            raise AppError(
                404,
                code="PENDING_ACTION_NOT_FOUND",
                detail="Không còn thao tác booking chờ xác nhận.",
            )
        if pending.confirmation_token != confirmation_token.upper():
            raise AppError(
                400,
                code="INVALID_CONFIRMATION_TOKEN",
                detail="Mã xác nhận không hợp lệ.",
            )

        payload = dict(pending.payload)
        if pending.action == "create_booking":
            idempotency_key = str(payload.pop("_idempotency_key"))
            result = await self._gateway.create_booking(payload, idempotency_key)
        else:
            booking_id = str(payload.pop("booking_id"))
            if pending.action == "cancel_booking":
                payload = {
                    "status": "cancelled",
                    "cancel_reason": payload.get("cancel_reason"),
                }
            result = await self._gateway.update_booking(booking_id, payload)

        await self._store.delete_pending(conversation_id)
        return result
