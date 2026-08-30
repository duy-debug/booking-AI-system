"""Application handler for loading POS-backed booking availability."""

from app.domain.booking_context import BookingContext
from app.domain.booking_models import (
    AvailabilityRequest,
    BookingContextNotReadyError,
    BookingGateway,
)
from app.domain.outcomes import HandlerOutcome, HandlerResult


class CheckAvailabilityHandler:
    """Loads slots for the complete booking shape without choosing one."""

    # Nhận gateway POS để kiểm tra slot dựa trên dữ liệu booking hiện tại.
    def __init__(self, booking_gateway: BookingGateway) -> None:
        self._booking_gateway = booking_gateway

    # Gọi POS lấy slot trống và map kết quả thành HandlerResult cho StateMachine.
    async def execute(self, context: BookingContext) -> HandlerResult:
        """Load slots without mutating the working booking context."""
        if (
            context.shop is None
            or context.booking_date is None
            or context.num_customer is None
            or context.duration_minutes is None
            or context.main_course is None
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
            main_course_id=course_selection.main_course.course_id,
            addon_ids=tuple(addon.course_id for addon in course_selection.addons),
            therapist_preference=context.therapist_preference,
            requested_start_time=context.requested_start_time,
        )
        availability = await self._booking_gateway.get_available_slots(request)
        slots = availability.slots
        if not slots:
            return HandlerResult(
                HandlerOutcome.NO_SLOTS,
                error_code=availability.status,
            )
        normalized_slots = tuple(slots)
        return HandlerResult(
            HandlerOutcome.SUCCESS,
            {"slots": normalized_slots},
            {"available_slots": normalized_slots},
        )
