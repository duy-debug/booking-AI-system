"""Temporary booking data collected during a conversation."""

from dataclasses import dataclass
from datetime import date, time
from uuid import UUID

from app.domain.booking import (
    Booking,
    BookingOption,
    CourseSelection,
    Customer,
    Service,
    Shop,
    TherapistPreference,
    TherapistPreferenceType,
)
from app.domain.booking_state import BookingState
from app.domain.exceptions import (
    InvalidBookingDataError,
    InvalidCourseSelectionError,
    InvalidCustomerCountError,
    InvalidDurationError,
    TherapistNotAllowedForGroupError,
)


@dataclass(slots=True)
class BookingContext:
    """Stores mutable booking data for an active conversation."""

    conversation_id: str
    state: BookingState = BookingState.IDLE
    shop: Shop | None = None
    service: Service | None = None
    customer: Customer | None = None
    booking_date: date | None = None
    start_time: time | None = None
    num_customer: int | None = None
    duration_minutes: int | None = None
    therapist_preference: TherapistPreference | None = None
    therapist_verified: bool = False
    options: tuple[BookingOption, ...] = ()
    addons: tuple[Service, ...] = ()
    available_slots: tuple[time, ...] | None = None
    booking_id: UUID | None = None
    phone: str | None = None
    phone_confirmed: bool = False
    member_rank: str | None = None
    visit_count: int | None = None
    ng_list_checked: bool = False
    is_ng_customer: bool = False
    booking: Booking | None = None
    reservation_code: str | None = None
    reservation_codes: tuple[str, ...] = ()
    child_reservation_ids: tuple[UUID, ...] = ()
    pending_action: str | None = None

    def is_ready_to_create(self) -> bool:
        """Return whether all data required to create a booking is present."""
        if (
            self.shop is None
            or self.service is None
            or self.customer is None
            or self.booking_date is None
            or self.start_time is None
            or self.num_customer is None
            or not 1 <= self.num_customer <= 3
            or self.duration_minutes is None
            or self.duration_minutes <= 0
            or self.duration_minutes % 15 != 0
            or self.phone is None
            or not self.phone_confirmed
            or not self.ng_list_checked
            or self.is_ng_customer
        ):
            return False

        try:
            CourseSelection(main_course=self.service, addons=self.addons)
        except InvalidCourseSelectionError:
            return False

        return not (
            self.num_customer >= 2
            and self.therapist_preference is not None
            and self.therapist_preference.preference_type
            is not TherapistPreferenceType.NONE
        )

    @property
    def course_selection(self) -> CourseSelection | None:
        """Return the selected main course and add-ons when present."""
        if self.service is None:
            return None
        return CourseSelection(main_course=self.service, addons=self.addons)

    def set_shop(self, shop: Shop | None) -> None:
        """Set a shop and invalidate shop-dependent selections."""
        if shop == self.shop:
            return
        self.shop = shop
        self._clear_course_and_availability()
        self.member_rank = None
        self.visit_count = None
        self.ng_list_checked = False
        self.is_ng_customer = False

    def set_booking_date(self, booking_date: date | None) -> None:
        """Set a date and invalidate date-dependent selections."""
        if booking_date == self.booking_date:
            return
        self.booking_date = booking_date
        self._clear_course_and_availability()

    def set_num_customer(self, value: int) -> None:
        """Set a valid number of customers."""
        if not 1 <= value <= 3:
            raise InvalidCustomerCountError(
                "Number of customers must be between one and three."
            )
        if value == self.num_customer:
            return
        self.num_customer = value
        self.available_slots = None
        self.start_time = None
        self.therapist_verified = False
        if value >= 2:
            self.therapist_preference = None

    def set_duration(self, value: int) -> None:
        """Set a positive duration divisible by 15 minutes."""
        if value <= 0 or value % 15 != 0:
            raise InvalidDurationError(
                "Booking duration must be positive and divisible by 15."
            )
        if value == self.duration_minutes:
            return
        self.duration_minutes = value
        self._clear_course_and_availability()

    def set_course_selection(self, selection: CourseSelection) -> None:
        """Set the main course and add-ons and invalidate availability."""
        self.service = selection.main_course
        self.addons = selection.addons
        self.options = ()
        self._clear_availability_and_therapist()

    def set_service(self, service: Service) -> None:
        """Set a compatible main service without add-ons."""
        self.set_course_selection(CourseSelection(main_course=service))

    def set_available_slots(self, slots: tuple[time, ...]) -> None:
        """Store the latest availability result."""
        self.available_slots = slots

    def set_start_time(self, start_time: time | None) -> None:
        """Set a time and require therapist revalidation."""
        self.start_time = start_time
        self.therapist_verified = False

    def set_therapist_preference(
        self,
        preference: TherapistPreference | None,
    ) -> None:
        """Set or clear the therapist preference."""
        if (
            self.num_customer is not None
            and self.num_customer >= 2
            and preference is not None
            and preference.preference_type is not TherapistPreferenceType.NONE
        ):
            raise TherapistNotAllowedForGroupError(
                "Group bookings cannot specify a therapist preference."
            )
        self.therapist_preference = preference
        self.therapist_verified = False

    def set_therapist_verified(self, verified: bool) -> None:
        """Store whether the selected therapist has been externally verified."""
        self.therapist_verified = verified

    def set_options(self, options: tuple[BookingOption, ...]) -> None:
        """Set compatible non-course options and invalidate availability."""
        option_ids = [option.option_id for option in options]
        if len(option_ids) != len(set(option_ids)):
            raise InvalidCourseSelectionError(
                "Booking options must have unique IDs."
            )
        self.options = options
        self._clear_availability_and_therapist()

    def set_phone(self, phone: str) -> None:
        """Store a phone number and reset all customer verification."""
        self.phone = phone
        self.phone_confirmed = False
        self.member_rank = None
        self.visit_count = None
        self.ng_list_checked = False
        self.is_ng_customer = False

    def confirm_phone(self) -> None:
        """Mark the stored phone number as confirmed."""
        if self.phone is None:
            raise InvalidBookingDataError("A phone number is required for confirmation.")
        self.phone_confirmed = True

    def set_customer_verification(
        self,
        *,
        member_rank: str | None,
        visit_count: int | None = None,
        is_ng_customer: bool,
    ) -> None:
        """Store member and NG-list results supplied by the application."""
        if self.phone is None:
            raise InvalidBookingDataError(
                "A phone number is required before customer verification."
            )
        self.member_rank = member_rank
        self.visit_count = visit_count
        self.ng_list_checked = True
        self.is_ng_customer = is_ng_customer

    def clear_phone(self) -> None:
        """Clear the phone number and its confirmation state."""
        self.phone = None
        self.phone_confirmed = False
        self.member_rank = None
        self.visit_count = None
        self.ng_list_checked = False
        self.is_ng_customer = False

    def _clear_course_and_availability(self) -> None:
        self.service = None
        self.addons = ()
        self.options = ()
        self._clear_availability_and_therapist()

    def _clear_availability_and_therapist(self) -> None:
        self.available_slots = None
        self.start_time = None
        self.therapist_preference = None
        self.therapist_verified = False

    def reset(self) -> None:
        """Clear temporary booking data while preserving the conversation ID."""
        self.state = BookingState.IDLE
        self.shop = None
        self.service = None
        self.customer = None
        self.booking_date = None
        self.start_time = None
        self.num_customer = None
        self.duration_minutes = None
        self.therapist_preference = None
        self.therapist_verified = False
        self.options = ()
        self.addons = ()
        self.available_slots = None
        self.booking_id = None
        self.phone = None
        self.phone_confirmed = False
        self.member_rank = None
        self.visit_count = None
        self.ng_list_checked = False
        self.is_ng_customer = False
        self.booking = None
        self.reservation_code = None
        self.reservation_codes = ()
        self.child_reservation_ids = ()
        self.pending_action = None
