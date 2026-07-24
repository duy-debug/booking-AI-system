from typing import Any

from app.application.create_booking_flow import CreateBookingFlow
from app.domain.intent import Intent
from app.domain.nlu import NLUResult


class BookingConversationHandler:
    # Nhận create flow đã cấu hình để handler chỉ chịu trách nhiệm dispatch intent.
    def __init__(self, create_booking_flow: CreateBookingFlow) -> None:
        self._create_booking_flow = create_booking_flow

    # Xác định dữ liệu còn thiếu; chỉ mutation tool mới được thực thi sau confirmation gate.
    async def handle(
        self,
        _query: str,
        nlu: NLUResult,
        conversation_id: str,
        selection: dict[str, Any] | None = None,
    ) -> dict:
        if nlu.intent is Intent.CREATE_BOOKING:
            return await self._create_booking_flow.handle(
                conversation_id=conversation_id,
                nlu=nlu,
                selection=selection,
            )
        if nlu.intent is Intent.LOOKUP_BOOKING:
            return {
                "answer": "Vui lòng cung cấp mã booking và xác thực số điện thoại.",
                "missing_entities": ["booking_id", "verification"],
                "conversation_id": conversation_id,
            }
        action = "đổi" if nlu.intent is Intent.UPDATE_BOOKING else "hủy"
        return {
            "answer": (f"Vui lòng cung cấp mã booking và xác thực khách hàng để {action} lịch."),
            "missing_entities": ["booking_id", "verification"],
            "conversation_id": conversation_id,
        }
