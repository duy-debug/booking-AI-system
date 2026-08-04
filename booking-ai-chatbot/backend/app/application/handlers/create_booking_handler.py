"""Application handler for safely creating an official booking."""

from app.application.exceptions import InvalidIdempotencyKeyError, SlotConflictError
from app.application.ports.booking_gateway import (
    BookingGateway,
    CreateBookingRequest,
    CreateBookingResult,
    FinalAvailabilityRequest,
)
from app.domain.booking_context import BookingContext
from app.domain.booking_rules import BookingRules


class CreateBookingHandler:
    """Performs final availability and one idempotent POS create call."""

    def __init__(self, booking_gateway: BookingGateway) -> None:
        self._booking_gateway = booking_gateway

    async def execute(
        self,
        context: BookingContext,
        idempotency_key: str,
    ) -> CreateBookingResult:
        """Validate, recheck availability and create without changing dialog state."""
        if not idempotency_key.strip():
            raise InvalidIdempotencyKeyError("Idempotency key must not be empty.")

        BookingRules.validate_create_context(context)

        assert context.shop is not None
        assert context.service is not None
        assert context.customer is not None
        assert context.booking_date is not None
        assert context.start_time is not None
        assert context.num_customer is not None
        assert context.duration_minutes is not None
        assert context.phone is not None

        addon_ids = tuple(addon.service_id for addon in context.addons)
        total_duration = context.total_duration_minutes or context.duration_minutes
        final_request = FinalAvailabilityRequest(
            shop_id=context.shop.shop_id,
            booking_date=context.booking_date,
            start_time=context.start_time,
            num_customer=context.num_customer,
            duration_minutes=total_duration,
            main_course_id=context.service.service_id,
            addon_ids=addon_ids,
            therapist_preference=context.therapist_preference,
        )
        final_result = await self._booking_gateway.check_final_availability(
            final_request
        )
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
            main_course_id=context.service.service_id,
            addon_ids=addon_ids,
            therapist_preference=context.therapist_preference,
            phone=context.phone,
            idempotency_key=idempotency_key,
            member_rank=context.member_rank,
            customer_name=context.customer.name,
        )
        result = await self._booking_gateway.create_booking(create_request)

        context.booking = result.booking
        context.booking_id = result.booking.booking_id
        context.reservation_code = (
            result.reservation_code or result.booking.reservation_code
        )
        context.reservation_codes = result.reservation_codes
        context.child_reservation_ids = tuple(
            child.reservation_id for child in result.child_reservations
        )
        return result
