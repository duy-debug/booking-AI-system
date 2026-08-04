"""Application handler for loading POS-backed booking availability."""

from datetime import time

from app.application.exceptions import SlotConflictError
from app.application.ports.booking_gateway import AvailabilityRequest, BookingGateway
from app.domain.booking_context import BookingContext
from app.domain.exceptions import BookingContextNotReadyError


class CheckAvailabilityHandler:
    """Loads slots for the complete booking shape without choosing one."""

    def __init__(self, booking_gateway: BookingGateway) -> None:
        self._booking_gateway = booking_gateway

    async def execute(self, context: BookingContext) -> tuple[time, ...]:
        """Load slots and store them without changing dialog state."""
        if (
            context.shop is None
            or context.booking_date is None
            or context.num_customer is None
            or context.duration_minutes is None
            or context.service is None
        ):
            raise BookingContextNotReadyError(
                "Shop, date, people, duration and main course are required."
            )

        course_selection = context.course_selection
        if course_selection is None:
            raise BookingContextNotReadyError("A main course is required.")
        request = AvailabilityRequest(
            shop_id=context.shop.shop_id,
            booking_date=context.booking_date,
            num_customer=context.num_customer,
            duration_minutes=context.total_duration_minutes or context.duration_minutes,
            main_course_id=course_selection.main_course.service_id,
            addon_ids=tuple(addon.service_id for addon in course_selection.addons),
            therapist_preference=context.therapist_preference,
        )
        slots = await self._booking_gateway.get_available_slots(request)
        context.set_available_slots(slots)
        if not slots:
            raise SlotConflictError(reason="No available slots for the booking shape.")
        return slots
