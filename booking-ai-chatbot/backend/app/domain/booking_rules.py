"""Domain rules for validating booking data."""

import re
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from app.domain.booking import TherapistPreferenceType
from app.domain.booking_context import BookingContext
from app.domain.exceptions import (
    BookingContextNotReadyError,
    CustomerNotAllowedError,
    CustomerVerificationRequiredError,
    InvalidBookingDataError,
    InvalidCustomerCountError,
    InvalidDurationError,
    PhoneNotConfirmedError,
    TherapistNotAllowedForGroupError,
)


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
        """Validate a positive duration divisible by 15 minutes."""
        if duration_minutes <= 0 or duration_minutes % 15 != 0:
            raise InvalidDurationError(
                "Service duration must be positive and divisible by 15."
            )

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
        customer = context.customer
        booking_date = context.booking_date
        start_time = context.start_time

        if (
            shop is None
            or customer is None
            or booking_date is None
            or start_time is None
        ):
            raise BookingContextNotReadyError("Booking context is incomplete.")

        if context.num_customer is None or not 1 <= context.num_customer <= 3:
            raise InvalidCustomerCountError(
                "Number of customers must be between one and three."
            )
        if context.duration_minutes is None:
            raise InvalidDurationError("Booking duration is required.")
        cls.validate_service_duration(context.duration_minutes)

        course_selection = context.course_selection
        if course_selection is None:
            raise BookingContextNotReadyError("A main course is required.")

        if (
            context.num_customer >= 2
            and context.therapist_preference is not None
            and context.therapist_preference.preference_type
            is TherapistPreferenceType.PERSONAL
        ):
            raise TherapistNotAllowedForGroupError(
                "Group bookings cannot specify a therapist preference."
            )

        if context.phone is None:
            raise BookingContextNotReadyError("A phone number is required.")
        cls.validate_phone(context.phone)
        if not context.phone_confirmed:
            raise PhoneNotConfirmedError("The phone number must be confirmed.")
        if not context.ng_list_checked:
            raise CustomerVerificationRequiredError(
                "Customer verification must complete before booking."
            )
        if context.is_ng_customer:
            raise CustomerNotAllowedError("This customer is not allowed to book.")

        cls.validate_phone(customer.phone)
        cls.validate_booking_datetime(booking_date, start_time)
