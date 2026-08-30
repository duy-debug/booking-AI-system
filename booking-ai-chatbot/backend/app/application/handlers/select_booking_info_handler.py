"""Validate and apply date, people and duration selections."""

from datetime import date

from app.domain.booking_context import BookingContext
from app.domain.outcomes import HandlerOutcome, HandlerResult


# Use case mutate các field booking cơ bản trong context nhưng không tự điều phối state.
class SelectBookingInfoHandler:
    """Owns non-I/O booking information updates."""

    # Validate ngày không nằm trong quá khứ trước khi cập nhật context.
    def select_date(self, context: BookingContext, value: date) -> HandlerResult:
        if value < date.today():
            return HandlerResult(HandlerOutcome.INVALID_INPUT, error_code="date_in_past")
        if context.last_unavailable_date is not None and value == context.last_unavailable_date:
            return HandlerResult(
                HandlerOutcome.INVALID_INPUT,
                error_code="date_still_unavailable",
            )
        return HandlerResult(
            HandlerOutcome.SUCCESS,
            context_updates={"booking_date": value},
        )

    # Validate số người trong phạm vi business hỗ trợ trước khi cập nhật context.
    def select_people(self, context: BookingContext, value: int) -> HandlerResult:
        if type(value) is not int or value <= 0:
            return HandlerResult(
                HandlerOutcome.INVALID_INPUT,
                error_code="num_customer_invalid",
            )
        if value > 3:
            return HandlerResult(
                HandlerOutcome.INVALID_INPUT,
                error_code="num_customer_too_many",
            )
        return HandlerResult(
            HandlerOutcome.SUCCESS,
            context_updates={"num_customer": value},
        )

    # Validate duration theo block 15 phút để khớp contract availability/POS.
    def select_duration(self, context: BookingContext, value: int) -> HandlerResult:
        if type(value) is not int or value <= 0:
            return HandlerResult(
                HandlerOutcome.INVALID_INPUT,
                error_code="invalid_duration",
            )
        return HandlerResult(
            HandlerOutcome.SUCCESS,
            context_updates={"duration_minutes": value},
        )
