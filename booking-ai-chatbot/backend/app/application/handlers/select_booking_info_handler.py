"""Validate and apply date, people and duration selections."""

from datetime import date

from app.domain.booking_context import BookingContext
from app.domain.outcomes import HandlerOutcome, HandlerResult


class SelectBookingInfoHandler:
    """Owns non-I/O booking information updates."""

    def select_date(self, context: BookingContext, value: date) -> HandlerResult:
        if value < date.today():
            return HandlerResult(HandlerOutcome.INVALID_INPUT, error_code="date_in_past")
        context.set_booking_date(value)
        return HandlerResult(
            HandlerOutcome.SUCCESS,
            context_updates={"booking_date": value},
        )

    def select_people(self, context: BookingContext, value: int) -> HandlerResult:
        if type(value) is not int or not 1 <= value <= 3:
            return HandlerResult(
                HandlerOutcome.INVALID_INPUT,
                error_code="num_customer_invalid",
            )
        context.set_num_customer(value)
        return HandlerResult(
            HandlerOutcome.SUCCESS,
            context_updates={"num_customer": value},
        )

    def select_duration(self, context: BookingContext, value: int) -> HandlerResult:
        if type(value) is not int or value <= 0 or value % 15:
            return HandlerResult(
                HandlerOutcome.INVALID_INPUT,
                error_code="duration_not_multiple_15",
            )
        context.set_duration(value)
        return HandlerResult(
            HandlerOutcome.SUCCESS,
            context_updates={"duration_minutes": value},
        )
