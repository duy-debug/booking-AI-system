"""Core data models for the booking domain."""
# ruff: noqa: E402

import re
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from app.domain.booking_context import BookingContext


class DomainError(Exception):
    """Base exception for all domain-level errors."""


class InvalidBookingDataError(DomainError):
    """Raised when booking data violates domain rules."""


class InvalidCustomerCountError(InvalidBookingDataError):
    """Raised when a booking has an unsupported number of customers."""


class InvalidDurationError(InvalidBookingDataError):
    """Raised when a booking duration violates domain rules."""


class InvalidCourseSelectionError(InvalidBookingDataError):
    """Raised when a main course and add-ons form an invalid selection."""


class TherapistNotAllowedForGroupError(InvalidBookingDataError):
    """Raised when a group booking specifies a therapist preference."""


class PhoneNotConfirmedError(InvalidBookingDataError):
    """Raised when booking creation is attempted with an unconfirmed phone."""


class CustomerVerificationRequiredError(InvalidBookingDataError):
    """Raised when member and NG-list verification has not completed."""


class CustomerNotAllowedError(InvalidBookingDataError):
    """Raised when customer verification disallows booking."""


class BookingContextNotReadyError(InvalidBookingDataError):
    """Raised when required booking context data is incomplete."""


class InvalidBookingStateError(DomainError):
    """Raised when an operation is invalid for the booking state."""


class BookingNotFoundError(DomainError):
    """Raised when a requested booking cannot be found."""


class BookingConflictError(DomainError):
    """Raised when a booking conflicts with an existing reservation."""


class CourseType(StrEnum):
    """Defines whether a main_course is a main course or an add-on."""

    MAIN = "main"
    ADDON = "addon"


class TherapistPreferenceType(StrEnum):
    """Defines how a customer prefers a therapist to be selected."""

    NONE = "none"
    MALE = "male"
    FEMALE = "female"
    PERSONAL = "personal"


@dataclass(frozen=True, slots=True)
class TherapistPreference:
    """Represents an optional therapist preference for a booking."""

    preference_type: TherapistPreferenceType
    therapist_id: str | None = None
    therapist_name: str | None = None

    def __post_init__(self) -> None:
        if (
            self.preference_type is TherapistPreferenceType.PERSONAL
            and self.therapist_id is None
            and self.therapist_name is None
        ):
            raise InvalidBookingDataError("A personal therapist preference requires an ID or name.")


@dataclass(frozen=True, slots=True)
class BookingOption:
    """Represents an optional booking selection."""

    option_id: str
    name: str


@dataclass(frozen=True, slots=True)
class Shop:
    """Represents a shop available for booking."""

    shop_id: UUID
    name: str
    address: str | None = None
    phone: str | None = None


@dataclass(frozen=True, slots=True)
class ShopTherapist:
    """Represents one therapist owned by a shop for deterministic matching."""

    therapist_id: UUID
    shop_id: UUID
    name: str
    gender: str


@dataclass(frozen=True, slots=True)
class Course:
    """Represents a POS course offered by a shop."""

    course_id: UUID
    name: str
    duration_minutes: int
    price: Decimal
    course_type: CourseType = CourseType.MAIN

    def __post_init__(self) -> None:
        if self.duration_minutes <= 0 or self.duration_minutes % 15 != 0:
            raise InvalidDurationError("Course duration must be positive and divisible by 15.")


@dataclass(frozen=True, slots=True)
class CourseSelection:
    """Represents exactly one main course and its optional add-ons."""

    main_course: Course
    addons: tuple[Course, ...] = ()

    def __post_init__(self) -> None:
        if self.main_course.course_type is not CourseType.MAIN:
            raise InvalidCourseSelectionError("The main course must have type MAIN.")
        if any(addon.course_type is not CourseType.ADDON for addon in self.addons):
            raise InvalidCourseSelectionError("Every add-on must have type ADDON.")

        course_ids = (self.main_course.course_id,) + tuple(addon.course_id for addon in self.addons)
        if len(course_ids) != len(set(course_ids)):
            raise InvalidCourseSelectionError("Course selection must contain unique course IDs.")


@dataclass(frozen=True, slots=True)
class Customer:
    """Represents the customer who makes a booking."""

    phone: str
    name: str | None = None


@dataclass(frozen=True, slots=True)
class Booking:
    """Represents a confirmed booking and its domain data."""

    booking_id: UUID
    status: str
    shop: Shop
    main_course: Course
    customer: Customer
    booking_date: date
    start_time: time
    num_customer: int = 1
    duration_minutes: int = 60
    therapist_preference: TherapistPreference | None = None
    options: tuple[BookingOption, ...] = ()
    addons: tuple[Course, ...] = ()
    reservation_code: str | None = None

    def __post_init__(self) -> None:
        if not 1 <= self.num_customer <= 3:
            raise InvalidCustomerCountError("Number of customers must be between one and three.")
        if self.duration_minutes <= 0 or self.duration_minutes % 15 != 0:
            raise InvalidDurationError("Booking duration must be positive and divisible by 15.")
        CourseSelection(main_course=self.main_course, addons=self.addons)
        if (
            self.num_customer >= 2
            and self.therapist_preference is not None
            and self.therapist_preference.preference_type is TherapistPreferenceType.PERSONAL
        ):
            raise TherapistNotAllowedForGroupError(
                "Group bookings cannot specify a therapist preference."
            )
        option_ids = [option.option_id for option in self.options]
        if len(option_ids) != len(set(option_ids)):
            raise InvalidCourseSelectionError("Booking options must have unique IDs.")

    @property
    def course_selection(self) -> CourseSelection:
        """Return the booking course selection."""
        return CourseSelection(main_course=self.main_course, addons=self.addons)


class BookingRules:
    """Validate booking data before backend submission."""

    _PHONE_PATTERN = re.compile(r"^\+?[0-9]{9,15}$")
    _VIETNAM_TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")

    @classmethod
    def validate_phone(cls, phone: str) -> None:
        normalized_phone = re.sub(r"[\s-]", "", phone)
        if cls._PHONE_PATTERN.fullmatch(normalized_phone) is None:
            raise InvalidBookingDataError("Invalid phone number.")

    @staticmethod
    def validate_course_duration(duration_minutes: int) -> None:
        if duration_minutes <= 0 or duration_minutes % 15 != 0:
            raise InvalidDurationError("Course duration must be positive and divisible by 15.")

    @classmethod
    def validate_booking_datetime(
        cls,
        booking_date: date,
        start_time: time,
        *,
        now: datetime | None = None,
    ) -> None:
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
    def validate_create_context(cls, context: "BookingContext") -> None:
        shop = context.shop
        customer = context.customer
        booking_date = context.booking_date
        start_time = context.start_time
        if shop is None or customer is None or booking_date is None or start_time is None:
            raise BookingContextNotReadyError("Booking context is incomplete.")
        if context.num_customer is None or not 1 <= context.num_customer <= 3:
            raise InvalidCustomerCountError("Number of customers must be between one and three.")
        if context.duration_minutes is None:
            raise InvalidDurationError("Booking duration is required.")
        cls.validate_course_duration(context.duration_minutes)
        if context.course_selection is None:
            raise BookingContextNotReadyError("A main course is required.")
        if (
            context.num_customer >= 2
            and context.therapist_preference is not None
            and context.therapist_preference.preference_type is TherapistPreferenceType.PERSONAL
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


"""Framework-independent application exceptions."""

from datetime import time


class ApplicationError(Exception):
    """Base exception for application use-case failures."""


class SlotConflictError(ApplicationError):
    """Raised when the selected slot fails the final availability check."""

    def __init__(
        self,
        nearest_slots: tuple[time, ...] = (),
        reason: str | None = None,
    ) -> None:
        super().__init__(reason or "The selected slot is no longer available.")
        self.nearest_slots = nearest_slots
        self.reason = reason


class CustomerVerificationMismatchError(ApplicationError):
    """Raised when POS verification returns data for a different phone."""


class InvalidIdempotencyKeyError(ApplicationError):
    """Raised when booking creation receives an empty idempotency key."""


"""Application contract for the external booking source of truth."""

from dataclasses import dataclass
from datetime import date, time
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class CourseSearchRequest:
    """Contains POS-supported filters for a shop course catalog."""

    shop_id: UUID
    course_type: CourseType | None = None
    is_active: bool = True


@dataclass(frozen=True, slots=True)
class ShopSearchCriteria:
    """Contains safely-evaluable constraints for the shop selection step."""

    booking_date: date | None = None
    requested_start_time: time | None = None
    num_customer: int | None = None
    duration_minutes: int | None = None
    requested_main_course_name: str | None = None
    requested_addon_name: str | None = None
    requested_therapist_name: str | None = None
    requested_therapist_gender: str | None = None


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
        raise InvalidCustomerCountError("Number of customers must be between one and three.")
    if duration_minutes <= 0 or duration_minutes % 15 != 0:
        raise InvalidDurationError("Booking duration must be positive and divisible by 15.")
    course_ids = (main_course_id,) + addon_ids
    if len(course_ids) != len(set(course_ids)):
        raise InvalidCourseSelectionError("Main course and add-on IDs must be unique.")
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
class AvailabilityWindowResult:
    """Contains display slots plus the business semantic for empty availability."""

    slots: tuple[time, ...]
    status: str = "available"


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
        if self.child_reservations and len(self.child_reservations) != self.booking.num_customer:
            raise ValueError("Child reservation count must match the booking customer count.")
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

    async def search_courses(
        self,
        request: CourseSearchRequest,
    ) -> list[Course]:
        """Return the POS course catalog matching supported filters."""
        ...

    async def get_available_slots(
        self,
        request: AvailabilityRequest,
    ) -> AvailabilityWindowResult:
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


class TherapistCatalogGateway(Protocol):
    """Optional POS capability for deterministic shop filtering by therapist ownership."""

    async def search_shop_therapists(
        self,
        shop_id: UUID,
        *,
        is_active: bool = True,
    ) -> list[ShopTherapist]:
        """Return active therapists belonging to one shop."""
        ...


"""Typed failures raised by the HTTP booking gateway."""


class BookingGatewayInfrastructureError(Exception):
    """Base error for failures at the POS HTTP boundary."""


class POSConnectionError(BookingGatewayInfrastructureError):
    """Raised when the POS cannot be reached."""


class POSTimeoutError(BookingGatewayInfrastructureError):
    """Raised when a POS request exceeds its configured timeout."""


class POSRequestMappingError(BookingGatewayInfrastructureError):
    """Raised when an application request cannot be represented by POS."""


class POSResponseMappingError(BookingGatewayInfrastructureError):
    """Raised when a successful POS response violates its declared schema."""


class POSContractNotConfiguredError(BookingGatewayInfrastructureError):
    """Raised when no verified POS contract exists for an operation."""


class POSHTTPError(BookingGatewayInfrastructureError):
    """Base error for a non-success POS HTTP response."""

    def __init__(
        self,
        *,
        operation: str,
        status_code: int,
        code: str | None,
    ) -> None:
        message = f"POS operation {operation!r} failed with HTTP {status_code}"
        if code is not None:
            message = f"{message} ({code})"
        super().__init__(message)
        self.operation = operation
        self.status_code = status_code
        self.code = code


class POSAuthenticationError(POSHTTPError):
    """Raised when POS rejects request authentication."""


class POSAuthorizationError(POSHTTPError):
    """Raised when POS denies access to an operation."""


class POSNotFoundError(POSHTTPError):
    """Raised when a requested POS resource does not exist."""


class POSValidationError(POSHTTPError):
    """Raised when POS rejects request data as invalid."""


class POSConflictError(POSHTTPError):
    """Raised when POS reports a conflicting operation."""


class POSTemporaryError(POSHTTPError):
    """Raised for rate limiting or temporary POS server failures."""


class POSUnexpectedStatusError(POSHTTPError):
    """Raised for an undocumented POS HTTP status."""
