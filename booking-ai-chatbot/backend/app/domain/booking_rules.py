"""Domain rules for validating booking data."""

import re
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from app.domain.booking_context import BookingContext
from app.domain.exceptions import InvalidBookingDataError


class BookingRules:
    """Validates basic booking data before backend submission."""

    _PHONE_PATTERN = re.compile(r"^\+?[0-9]{9,15}$")
    _VIETNAM_TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")

    @classmethod
    def validate_phone(cls, phone: str) -> None:
        """Validate a phone number after removing spaces and hyphens."""
        normalized_phone = re.sub(r"[\s-]", "", phone)
        if cls._PHONE_PATTERN.fullmatch(normalized_phone) is None:
            raise InvalidBookingDataError("Invalid phone number.")

    @staticmethod
    def validate_service_duration(duration_minutes: int) -> None:
        """Validate that a service duration is greater than zero."""
        if duration_minutes <= 0:
            raise InvalidBookingDataError("Service duration must be greater than zero.")

    @classmethod
    def validate_booking_datetime(
        cls,
        booking_date: date,
        start_time: time,
        *,
        now: datetime | None = None,
    ) -> None:
        """Validate that the booking date and time are in the future."""
        booking_datetime = datetime.combine(
            booking_date,
            start_time,
            tzinfo=cls._VIETNAM_TIMEZONE,
        )
        current_datetime = now or datetime.now(cls._VIETNAM_TIMEZONE)
        if current_datetime.tzinfo is None:
            current_datetime = current_datetime.replace(tzinfo=cls._VIETNAM_TIMEZONE)
        else:
            current_datetime = current_datetime.astimezone(cls._VIETNAM_TIMEZONE)

        if booking_datetime <= current_datetime:
            raise InvalidBookingDataError("Booking date and time must be in the future.")

    @classmethod
    def validate_create_context(cls, context: BookingContext) -> None:
        """Validate a complete context before creating a booking."""
        shop = context.shop
        service = context.service
        customer = context.customer
        booking_date = context.booking_date
        start_time = context.start_time

        if (
            shop is None
            or service is None
            or customer is None
            or booking_date is None
            or start_time is None
        ):
            raise InvalidBookingDataError("Booking context is incomplete.")

        cls.validate_phone(customer.phone)
        cls.validate_service_duration(service.duration_minutes)
        cls.validate_booking_datetime(booking_date, start_time)
