"""Application handler for safely creating an official booking."""

from app.domain.booking_context import BookingContext
from app.domain.booking_models import (
    BookingGateway,
    BookingRules,
    CreateBookingRequest,
    FinalAvailabilityRequest,
    InvalidIdempotencyKeyError,
    SlotConflictError,
)
from app.domain.outcomes import HandlerOutcome, HandlerResult


class CreateBookingHandler:
    """Performs final availability and one idempotent POS create call."""

    # Nhận gateway POS dùng cho final availability và create booking thật.
    def __init__(self, booking_gateway: BookingGateway) -> None:
        self._booking_gateway = booking_gateway

    # Recheck availability rồi gọi POS create một lần với idempotency key ổn định.
    async def execute(
        self,
        context: BookingContext,
        idempotency_key: str,
    ) -> HandlerResult:
        """Validate, recheck availability and create without changing dialog state."""
        if not idempotency_key.strip():
            raise InvalidIdempotencyKeyError("Idempotency key must not be empty.")

        BookingRules.validate_create_context(context)

        assert context.shop is not None
        assert context.main_course is not None
        assert context.customer is not None
        assert context.booking_date is not None
        assert context.start_time is not None
        assert context.num_customer is not None
        assert context.duration_minutes is not None
        assert context.phone is not None

        addon_ids = tuple(addon.course_id for addon in context.addons)
        total_duration = context.total_duration_minutes or context.duration_minutes
        final_request = FinalAvailabilityRequest(
            shop_id=context.shop.shop_id,
            booking_date=context.booking_date,
            start_time=context.start_time,
            num_customer=context.num_customer,
            duration_minutes=total_duration,
            main_course_id=context.main_course.course_id,
            addon_ids=addon_ids,
            therapist_preference=context.therapist_preference,
        )
        final_result = await self._booking_gateway.check_final_availability(final_request)
        if not final_result.available:
            raise SlotConflictError(
                nearest_slots=final_result.nearest_slots,
                reason=final_result.reason,
            )

        create_request = CreateBookingRequest(
            shop_id=context.shop.shop_id,
            booking_date=context.booking_date,
            start_time=context.start_time,
            num_customer=context.num_customer,
            duration_minutes=total_duration,
            main_course_id=context.main_course.course_id,
            addon_ids=addon_ids,
            therapist_preference=context.therapist_preference,
            phone=context.phone,
            idempotency_key=idempotency_key,
            member_rank=context.member_rank,
            customer_name=context.customer.name,
        )
        result = await self._booking_gateway.create_booking(create_request)

        reservation_code = result.reservation_code or result.booking.reservation_code
        return HandlerResult(
            HandlerOutcome.SUCCESS,
            {"create_result": result},
            {
                "booking": result.booking,
                "booking_id": result.booking.booking_id,
                "reservation_code": reservation_code,
            },
        )
