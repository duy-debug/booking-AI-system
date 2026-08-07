"""Temporary booking data collected during a conversation."""

from dataclasses import dataclass, field
from datetime import date, time
from enum import StrEnum
from uuid import UUID, uuid4

from app.domain.booking_models import (
    Booking,
    Course,
    CourseSelection,
    Customer,
    InvalidBookingDataError,
    InvalidCourseSelectionError,
    InvalidCustomerCountError,
    InvalidDurationError,
    Shop,
    TherapistNotAllowedForGroupError,
    TherapistPreference,
    TherapistPreferenceType,
)
from app.domain.booking_state import BookingState


class CourseSelectionMode(StrEnum):
    """Authoritative sub-step while the public dialog state selects courses."""

    NONE = "none"
    MAIN = "main_course"
    ADDON = "addon"


@dataclass(slots=True)
class BookingContext:
    """Stores mutable booking data for an active conversation."""

    conversation_id: str
    state: BookingState = BookingState.IDLE
    turn_sequence: int = field(default=0, compare=False)
    shop: Shop | None = None
    requested_shop_name: str | None = None
    suggested_shops: tuple[Shop, ...] = ()
    suggested_shops_loaded: bool = False
    main_course: Course | None = None
    course_selection_mode: CourseSelectionMode = CourseSelectionMode.NONE
    customer: Customer | None = None
    customer_id: str | None = None
    booking_date: date | None = None
    requested_booking_date: date | None = None
    start_time: time | None = None
    requested_start_time: time | None = None
    num_customer: int | None = None
    requested_num_customer: int | None = None
    duration_minutes: int | None = None
    requested_duration_minutes: int | None = None
    requested_main_course_name: str | None = None
    requested_addon_name: str | None = None
    requested_skip_addon: bool = False
    requested_therapist_name: str | None = None
    requested_therapist_gender: str | None = None
    requested_phone: str | None = None
    requested_customer_name: str | None = None
    therapist_preference: TherapistPreference | None = None
    therapist_verified: bool = False
    addons: tuple[Course, ...] = ()
    available_slots: tuple[time, ...] | None = None
    booking_id: UUID | None = None
    phone: str | None = None
    phone_confirmed: bool = False
    member_rank: str | None = None
    ng_list_checked: bool = False
    is_ng_customer: bool = False
    booking: Booking | None = None
    reservation_code: str | None = None
    booking_attempt_id: str | None = None
    last_failure_code: str | None = None

    @property
    def shop_id(self) -> UUID | None:
        return self.shop.shop_id if self.shop is not None else None

    @property
    def shop_name(self) -> str | None:
        return self.shop.name if self.shop is not None else None

    @property
    def people_count(self) -> int | None:
        return self.num_customer

    @property
    def main_course_id(self) -> UUID | None:
        return self.main_course.course_id if self.main_course is not None else None

    @property
    def main_course_name(self) -> str | None:
        return self.main_course.name if self.main_course is not None else None

    @property
    def addon_ids(self) -> tuple[UUID, ...]:
        return tuple(addon.course_id for addon in self.addons)

    @property
    def therapist_id(self) -> str | None:
        return (
            self.therapist_preference.therapist_id
            if self.therapist_preference is not None
            else None
        )

    @property
    def therapist_name(self) -> str | None:
        return (
            self.therapist_preference.therapist_name
            if self.therapist_preference is not None
            else None
        )

    @property
    def skip_therapist(self) -> bool:
        return self.therapist_preference is None and self.therapist_verified

    @property
    def customer_name(self) -> str | None:
        return self.customer.name if self.customer is not None else None

    @property
    def ng_list_status(self) -> str:
        if not self.ng_list_checked:
            return "unchecked"
        return "blocked" if self.is_ng_customer else "allowed"

    @property
    def confirmation_status(self) -> str:
        if self.state is BookingState.COMPLETED:
            return "completed"
        return "confirmed" if self.phone_confirmed else "pending"

    @property
    def total_duration_minutes(self) -> int | None:
        """Return the POS-authoritative total duration of selected courses."""
        if self.main_course is None:
            return self.duration_minutes
        return self.main_course.duration_minutes + sum(
            addon.duration_minutes for addon in self.addons
        )

    def is_ready_to_create(self) -> bool:
        """Return whether all data required to create a booking is present."""
        if (
            self.shop is None
            or self.main_course is None
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
            CourseSelection(main_course=self.main_course, addons=self.addons)
        except InvalidCourseSelectionError:
            return False

        return not (
            self.num_customer >= 2
            and self.therapist_preference is not None
            and self.therapist_preference.preference_type is not TherapistPreferenceType.NONE
        )

    def begin_turn(self) -> int:
        """Advance and return the conversation-local trace sequence."""
        self.turn_sequence += 1
        return self.turn_sequence

    def ensure_booking_attempt_id(self) -> str:
        """Return the server-owned identifier for the current booking attempt."""
        if self.booking_attempt_id is None:
            self.booking_attempt_id = str(uuid4())
        return self.booking_attempt_id

    def clear_booking_attempt(self) -> None:
        """Invalidate idempotency when booking-defining data changes."""
        self.booking_attempt_id = None

    @property
    def course_selection(self) -> CourseSelection | None:
        """Return the selected main course and add-ons when present."""
        if self.main_course is None:
            return None
        return CourseSelection(main_course=self.main_course, addons=self.addons)

    def set_shop(self, shop: Shop | None) -> None:
        """Set a shop and invalidate shop-dependent selections."""
        if shop == self.shop:
            return
        self.clear_booking_attempt()
        self.shop = shop
        self.suggested_shops = ()
        self.suggested_shops_loaded = False
        self._clear_course_and_availability()
        self.member_rank = None
        self.ng_list_checked = False
        self.is_ng_customer = False

    def set_booking_date(self, booking_date: date | None) -> None:
        """Set a date and invalidate date-dependent selections."""
        if booking_date == self.booking_date:
            return
        self.clear_booking_attempt()
        self.booking_date = booking_date
        self._clear_course_and_availability()

    def set_num_customer(self, value: int) -> None:
        """Set a valid number of customers."""
        if not 1 <= value <= 3:
            raise InvalidCustomerCountError("Number of customers must be between one and three.")
        if value == self.num_customer:
            return
        self.clear_booking_attempt()
        self.num_customer = value
        self.available_slots = None
        self.start_time = None
        self.therapist_verified = False
        if value >= 2:
            self.therapist_preference = None

    def set_duration(self, value: int) -> None:
        """Set a positive duration divisible by 15 minutes."""
        if value <= 0 or value % 15 != 0:
            raise InvalidDurationError("Booking duration must be positive and divisible by 15.")
        if value == self.duration_minutes:
            return
        self.clear_booking_attempt()
        self.duration_minutes = value
        self._clear_course_and_availability()
        self.course_selection_mode = CourseSelectionMode.MAIN

    def set_course_selection(self, selection: CourseSelection) -> None:
        """Set the main course and add-ons and invalidate availability."""
        if selection != self.course_selection:
            self.clear_booking_attempt()
        self.main_course = selection.main_course
        self.addons = selection.addons
        self._clear_availability_and_therapist()
        self.course_selection_mode = (
            CourseSelectionMode.ADDON if not selection.addons else CourseSelectionMode.NONE
        )

    def skip_addon(self) -> None:
        """Finish the optional add-on sub-step without changing the main course."""
        self.course_selection_mode = CourseSelectionMode.NONE

    def set_course(self, course: Course) -> None:
        """Set a compatible main course without add-ons."""
        self.set_course_selection(CourseSelection(main_course=course))

    def set_available_slots(self, slots: tuple[time, ...]) -> None:
        """Store the latest availability result."""
        self.available_slots = slots

    def set_start_time(self, start_time: time | None) -> None:
        """Set a time and require therapist revalidation."""
        if start_time != self.start_time:
            self.clear_booking_attempt()
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
            and preference.preference_type is TherapistPreferenceType.PERSONAL
        ):
            raise TherapistNotAllowedForGroupError(
                "Group bookings cannot specify a therapist preference."
            )
        if preference != self.therapist_preference:
            self.clear_booking_attempt()
        self.therapist_preference = preference
        self.therapist_verified = False

    def set_therapist_verified(self, verified: bool) -> None:
        """Store whether the selected therapist has been externally verified."""
        self.therapist_verified = verified

    def set_phone(self, phone: str) -> None:
        """Store a phone number and reset all customer verification."""
        if phone != self.phone:
            self.clear_booking_attempt()
        self.phone = phone
        self.customer = None
        self.customer_id = None
        self.phone_confirmed = False
        self.member_rank = None
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
        is_ng_customer: bool,
    ) -> None:
        """Store member and NG-list results supplied by the application."""
        if self.phone is None:
            raise InvalidBookingDataError(
                "A phone number is required before customer verification."
            )
        self.member_rank = member_rank
        self.ng_list_checked = True
        self.is_ng_customer = is_ng_customer

    def clear_phone(self) -> None:
        """Clear the phone number and its confirmation state."""
        self.phone = None
        self.phone_confirmed = False
        self.member_rank = None
        self.ng_list_checked = False
        self.is_ng_customer = False

    def change_shop(self, shop: Shop | None) -> None:
        """Replace the shop and clear only shop-dependent booking data."""
        self.shop = shop
        self.main_course = None
        self.addons = ()
        self._clear_availability_and_therapist()
        self.member_rank = None
        self.ng_list_checked = False
        self.is_ng_customer = False
        self._clear_booking_result()

    def change_booking_date(self, booking_date: date | None) -> None:
        """Replace the date while preserving shop, course and customer choices."""
        self.booking_date = booking_date
        self._clear_availability_and_therapist()
        self._clear_booking_result()

    def change_num_customer(self, value: int | None) -> None:
        """Replace the party size after validating its domain range."""
        if value is not None and not 1 <= value <= 3:
            raise InvalidCustomerCountError("Number of customers must be between one and three.")
        self.num_customer = value
        self._clear_availability_and_therapist()
        self._clear_booking_result()

    def change_duration(self, value: int | None) -> None:
        """Replace duration and invalidate its course and slot dependencies."""
        if value is not None and (value <= 0 or value % 15 != 0):
            raise InvalidDurationError("Booking duration must be positive and divisible by 15.")
        self.duration_minutes = value
        self.main_course = None
        self.addons = ()
        self._clear_availability_and_therapist()
        self._clear_booking_result()
        self.course_selection_mode = (
            CourseSelectionMode.MAIN if value is not None else CourseSelectionMode.NONE
        )

    def change_course_selection(
        self,
        selection: CourseSelection | None,
    ) -> None:
        """Replace the course selection while preserving its selected shop."""
        if selection is None:
            self.main_course = None
            self.addons = ()
        else:
            self.main_course = selection.main_course
            self.addons = selection.addons
        self._clear_availability_and_therapist()
        self._clear_booking_result()
        self.course_selection_mode = (
            CourseSelectionMode.MAIN if selection is None else CourseSelectionMode.ADDON
        )

    def change_start_time(self, start_time: time | None) -> None:
        """Replace the selected time and invalidate therapist confirmation."""
        self.start_time = start_time
        self.therapist_preference = None
        self.therapist_verified = False
        self._clear_booking_result()

    def change_therapist_preference(
        self,
        preference: TherapistPreference | None,
    ) -> None:
        """Replace therapist preference without clearing the selected slot."""
        if (
            self.num_customer is not None
            and self.num_customer >= 2
            and preference is not None
            and preference.preference_type is TherapistPreferenceType.PERSONAL
        ):
            raise TherapistNotAllowedForGroupError(
                "Group bookings cannot specify a therapist preference."
            )
        self.therapist_preference = preference
        self.therapist_verified = False
        self._clear_booking_result()

    def change_phone(self, phone: str | None) -> None:
        """Replace customer phone data without clearing booking selections."""
        self.customer = None
        self.customer_id = None
        self.clear_phone()
        if phone is not None:
            self.phone = phone
        self._clear_booking_result()

    def _clear_course_and_availability(self) -> None:
        self.main_course = None
        self.addons = ()
        self._clear_availability_and_therapist()
        self.course_selection_mode = CourseSelectionMode.MAIN

    def _clear_availability_and_therapist(self) -> None:
        self.available_slots = None
        self.start_time = None
        self.therapist_preference = None
        self.therapist_verified = False

    def _clear_booking_result(self) -> None:
        self.clear_booking_attempt()
        self.booking_id = None
        self.booking = None
        self.reservation_code = None
        self.last_failure_code = None

    def reset(self) -> None:
        """Clear temporary booking data while preserving the conversation ID."""
        turn_sequence = self.turn_sequence
        self.state = BookingState.IDLE
        self.shop = None
        self.requested_shop_name = None
        self.main_course = None
        self.customer = None
        self.booking_date = None
        self.requested_booking_date = None
        self.start_time = None
        self.requested_start_time = None
        self.num_customer = None
        self.requested_num_customer = None
        self.duration_minutes = None
        self.requested_duration_minutes = None
        self.requested_main_course_name = None
        self.requested_addon_name = None
        self.requested_skip_addon = False
        self.requested_therapist_name = None
        self.requested_therapist_gender = None
        self.requested_phone = None
        self.requested_customer_name = None
        self.therapist_preference = None
        self.therapist_verified = False
        self.addons = ()
        self.available_slots = None
        self.booking_id = None
        self.phone = None
        self.phone_confirmed = False
        self.member_rank = None
        self.ng_list_checked = False
        self.is_ng_customer = False
        self.booking = None
        self.reservation_code = None
        self.booking_attempt_id = None
        self.course_selection_mode = CourseSelectionMode.NONE
        self.last_failure_code = None
        self.turn_sequence = turn_sequence

    def restart_booking(self) -> None:
        """Reset booking data and enter the first selection state."""
        self.reset()
        self.state = BookingState.SELECTING_SHOP

    def enter_shop_selection(self) -> None:
        """Enter shop selection for a read-only shop discovery turn."""
        if self.state is not BookingState.IDLE:
            raise InvalidBookingDataError("Shop discovery can only start a booking from idle.")
        self.state = BookingState.SELECTING_SHOP

    def enter_time_selection(self) -> None:
        """Enter time selection after externally loading current slots."""
        if self.available_slots is None:
            raise InvalidBookingDataError("Available slots are required before time selection.")
        self.state = BookingState.SELECTING_TIME
