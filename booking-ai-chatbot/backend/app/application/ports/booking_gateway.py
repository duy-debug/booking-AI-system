"""Application contract for the external booking source of truth."""

from dataclasses import dataclass
from datetime import date, time
from typing import Protocol
from uuid import UUID

from app.domain.booking import (
    Booking,
    Service,
    Shop,
    TherapistPreference,
    TherapistPreferenceType,
)
from app.domain.exceptions import (
    InvalidCourseSelectionError,
    InvalidCustomerCountError,
    InvalidDurationError,
    TherapistNotAllowedForGroupError,
)


def _validate_booking_shape(
    *,
    num_customer: int,
    duration_minutes: int,
    main_course_id: UUID,
    addon_ids: tuple[UUID, ...],
    therapist_preference: TherapistPreference | None,
) -> None:
    if not 1 <= num_customer <= 3:
        raise InvalidCustomerCountError(
            "Number of customers must be between one and three."
        )
    if duration_minutes <= 0 or duration_minutes % 15 != 0:
        raise InvalidDurationError(
            "Booking duration must be positive and divisible by 15."
        )
    service_ids = (main_course_id,) + addon_ids
    if len(service_ids) != len(set(service_ids)):
        raise InvalidCourseSelectionError(
            "Main course and add-on IDs must be unique."
        )
    if (
        num_customer >= 2
        and therapist_preference is not None
        and therapist_preference.preference_type is not TherapistPreferenceType.NONE
    ):
        raise TherapistNotAllowedForGroupError(
            "Group bookings cannot specify a therapist preference."
        )


@dataclass(frozen=True, slots=True)
class AvailabilityRequest:
    """Contains all inputs that affect display availability."""

    shop_id: UUID
    booking_date: date
    num_customer: int
    duration_minutes: int
    main_course_id: UUID
    addon_ids: tuple[UUID, ...] = ()
    therapist_preference: TherapistPreference | None = None

    def __post_init__(self) -> None:
        _validate_booking_shape(
            num_customer=self.num_customer,
            duration_minutes=self.duration_minutes,
            main_course_id=self.main_course_id,
            addon_ids=self.addon_ids,
            therapist_preference=self.therapist_preference,
        )


@dataclass(frozen=True, slots=True)
class CustomerVerificationResult:
    """Contains authoritative customer verification data returned by POS."""

    phone: str
    customer_id: str | None
    member_rank: str | None
    visit_count: int | None
    ng_list_checked: bool
    is_ng_customer: bool


@dataclass(frozen=True, slots=True)
class FinalAvailabilityRequest:
    """Contains all inputs required to recheck a selected slot."""

    shop_id: UUID
    booking_date: date
    start_time: time
    num_customer: int
    duration_minutes: int
    main_course_id: UUID
    addon_ids: tuple[UUID, ...] = ()
    therapist_preference: TherapistPreference | None = None

    def __post_init__(self) -> None:
        _validate_booking_shape(
            num_customer=self.num_customer,
            duration_minutes=self.duration_minutes,
            main_course_id=self.main_course_id,
            addon_ids=self.addon_ids,
            therapist_preference=self.therapist_preference,
        )


@dataclass(frozen=True, slots=True)
class FinalAvailabilityResult:
    """Reports final slot availability and optional recovery information."""

    available: bool
    nearest_slots: tuple[time, ...] = ()
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class CreateBookingRequest:
    """Contains the immutable payload required to create a booking."""

    shop_id: UUID
    booking_date: date
    start_time: time
    num_customer: int
    duration_minutes: int
    main_course_id: UUID
    addon_ids: tuple[UUID, ...]
    therapist_preference: TherapistPreference | None
    phone: str
    idempotency_key: str
    member_rank: str | None = None

    def __post_init__(self) -> None:
        _validate_booking_shape(
            num_customer=self.num_customer,
            duration_minutes=self.duration_minutes,
            main_course_id=self.main_course_id,
            addon_ids=self.addon_ids,
            therapist_preference=self.therapist_preference,
        )


@dataclass(frozen=True, slots=True)
class CreateBookingResult:
    """Contains the official booking and reservation identifiers returned by POS."""

    booking: Booking
    reservation_code: str | None = None
    reservation_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        codes = (() if self.reservation_code is None else (self.reservation_code,)) + (
            self.reservation_codes
        )
        if len(codes) != len(set(codes)):
            raise ValueError("Reservation codes must be unique.")


class BookingGateway(Protocol):
    """Defines booking operations required by the application layer."""

    async def search_shops(self, query: str | None = None) -> list[Shop]:
        """Return shops matching an optional search query."""
        ...

    async def search_services(
        self,
        shop_id: UUID,
        booking_date: date,
        query: str | None = None,
    ) -> list[Service]:
        """Return the shop course catalog available for a date."""
        ...

    async def get_available_slots(
        self,
        request: AvailabilityRequest,
    ) -> tuple[time, ...]:
        """Return display availability for the complete booking shape."""
        ...

    async def verify_customer(
        self,
        phone: str,
    ) -> CustomerVerificationResult:
        """Return authoritative member and NG-list verification."""
        ...

    async def check_final_availability(
        self,
        request: FinalAvailabilityRequest,
    ) -> FinalAvailabilityResult:
        """Recheck a selected slot immediately before booking creation."""
        ...

    async def create_booking(
        self,
        request: CreateBookingRequest,
    ) -> CreateBookingResult:
        """Create and return an official booking result."""
        ...

    async def lookup_booking(self, booking_id: UUID) -> Booking:
        """Return an official booking by its identifier."""
        ...

    async def reschedule_booking(
        self,
        booking_id: UUID,
        booking_date: date,
        start_time: time,
    ) -> Booking:
        """Reschedule and return the updated official booking."""
        ...

    async def cancel_booking(self, booking_id: UUID) -> Booking:
        """Cancel and return the updated official booking."""
        ...
