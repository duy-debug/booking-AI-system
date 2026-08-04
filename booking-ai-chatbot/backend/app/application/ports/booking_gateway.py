"""Application contract for the external booking source of truth."""

from dataclasses import dataclass
from datetime import date, time
from typing import Protocol
from uuid import UUID

from app.domain.booking import (
    Booking,
    CourseType,
    Service,
    Shop,
    TherapistPreference,
    TherapistPreferenceType,
)
from app.domain.exceptions import (
    InvalidBookingDataError,
    InvalidCourseSelectionError,
    InvalidCustomerCountError,
    InvalidDurationError,
    TherapistNotAllowedForGroupError,
)


@dataclass(frozen=True, slots=True)
class CourseSearchRequest:
    """Contains POS-supported filters for a shop course catalog."""

    shop_id: UUID
    course_type: CourseType | None = None
    is_active: bool = True


@dataclass(frozen=True, slots=True)
class AvailableTherapistRequest:
    """Contains the selected booking window used to list available therapists."""

    shop_id: UUID
    booking_date: date
    start_time: time
    end_time: time
    gender: TherapistPreferenceType | None = None


@dataclass(frozen=True, slots=True)
class CustomerVerificationRequest:
    """Contains the shop and normalized phone required by POS eligibility."""

    shop_id: UUID
    phone: str

    def __post_init__(self) -> None:
        if not self.phone:
            raise InvalidBookingDataError("Customer verification phone is required.")


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
        and therapist_preference.preference_type is TherapistPreferenceType.PERSONAL
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
    customer_name: str | None = None


@dataclass(frozen=True, slots=True)
class ChildReservationReference:
    """Identifies one participant reservation created under a booking."""

    reservation_id: UUID
    participant_index: int | None = None


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
    customer_name: str | None = None

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
    child_reservations: tuple[ChildReservationReference, ...] = ()

    def __post_init__(self) -> None:
        child_ids = [item.reservation_id for item in self.child_reservations]
        if len(child_ids) != len(set(child_ids)):
            raise ValueError("Child reservation IDs must be unique.")
        participant_indexes = [
            item.participant_index
            for item in self.child_reservations
            if item.participant_index is not None
        ]
        if len(participant_indexes) != len(set(participant_indexes)):
            raise ValueError("Child reservation participant indexes must be unique.")
        if (
            self.child_reservations
            and len(self.child_reservations) != self.booking.num_customer
        ):
            raise ValueError(
                "Child reservation count must match the booking customer count."
            )
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
        request: CourseSearchRequest,
    ) -> list[Service]:
        """Return the POS course catalog matching supported filters."""
        ...

    async def get_available_slots(
        self,
        request: AvailabilityRequest,
    ) -> tuple[time, ...]:
        """Return display availability for the complete booking shape."""
        ...

    async def verify_customer(
        self,
        request: CustomerVerificationRequest,
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


class TherapistAvailabilityGateway(Protocol):
    """Optional POS capability for resolving therapists after time selection."""

    async def search_available_therapists(
        self,
        request: AvailableTherapistRequest,
    ) -> list[TherapistPreference]:
        """Return POS-authoritative therapists available for one selected window."""
        ...
