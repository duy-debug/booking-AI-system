from typing import Any

from app.application.create_booking_flow import CreateBookingFlow
from app.application.lookup_booking_flow import LookupBookingFlow
from app.application.manage_booking_flow import ManageBookingFlow
from app.domain.intent import Intent
from app.domain.nlu import NLUResult


class BookingConversationHandler:
    # Nhận từng workflow qua constructor để handler chỉ chịu trách nhiệm dispatch intent.
    def __init__(
        self,
        create_booking_flow: CreateBookingFlow,
        lookup_booking_flow: LookupBookingFlow,
        update_booking_flow: ManageBookingFlow,
        cancel_booking_flow: ManageBookingFlow,
    ) -> None:
        self._create_booking_flow = create_booking_flow
        self._lookup_booking_flow = lookup_booking_flow
        self._update_booking_flow = update_booking_flow
        self._cancel_booking_flow = cancel_booking_flow

    # Chuyển từng booking intent sang workflow tương ứng, không gọi integration trực tiếp.
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
            return await self._lookup_booking_flow.handle(
                conversation_id=conversation_id,
                nlu=nlu,
                selection=selection,
            )
        flow = (
            self._update_booking_flow
            if nlu.intent is Intent.UPDATE_BOOKING
            else self._cancel_booking_flow
        )
        return await flow.handle(conversation_id, nlu, selection)
