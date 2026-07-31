"""Core data models for the booking domain."""

from dataclasses import dataclass
from datetime import date, time
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from app.domain.exceptions import (
    InvalidBookingDataError,
    InvalidCourseSelectionError,
    InvalidCustomerCountError,
    InvalidDurationError,
    TherapistNotAllowedForGroupError,
)


class CourseType(StrEnum):
    """Defines whether a service is a main course or an add-on."""

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
            raise InvalidBookingDataError(
                "A personal therapist preference requires an ID or name."
            )


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
class Service:
    """Represents a service offered by a shop."""

    service_id: UUID
    name: str
    duration_minutes: int
    price: Decimal
    course_type: CourseType = CourseType.MAIN

    def __post_init__(self) -> None:
        if self.duration_minutes <= 0 or self.duration_minutes % 15 != 0:
            raise InvalidDurationError(
                "Service duration must be positive and divisible by 15."
            )


@dataclass(frozen=True, slots=True)
class CourseSelection:
    """Represents exactly one main course and its optional add-ons."""

    main_course: Service
    addons: tuple[Service, ...] = ()

    def __post_init__(self) -> None:
        if self.main_course.course_type is not CourseType.MAIN:
            raise InvalidCourseSelectionError("The main course must have type MAIN.")
        if any(addon.course_type is not CourseType.ADDON for addon in self.addons):
            raise InvalidCourseSelectionError("Every add-on must have type ADDON.")

        service_ids = (self.main_course.service_id,) + tuple(
            addon.service_id for addon in self.addons
        )
        if len(service_ids) != len(set(service_ids)):
            raise InvalidCourseSelectionError(
                "Course selection must contain unique service IDs."
            )


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
    service: Service
    customer: Customer
    booking_date: date
    start_time: time
    num_customer: int = 1
    duration_minutes: int = 60
    therapist_preference: TherapistPreference | None = None
    options: tuple[BookingOption, ...] = ()
    addons: tuple[Service, ...] = ()
    reservation_code: str | None = None

    def __post_init__(self) -> None:
        if not 1 <= self.num_customer <= 3:
            raise InvalidCustomerCountError(
                "Number of customers must be between one and three."
            )
        if self.duration_minutes <= 0 or self.duration_minutes % 15 != 0:
            raise InvalidDurationError(
                "Booking duration must be positive and divisible by 15."
            )
        CourseSelection(main_course=self.service, addons=self.addons)
        if (
            self.num_customer >= 2
            and self.therapist_preference is not None
            and self.therapist_preference.preference_type
            is not TherapistPreferenceType.NONE
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
        return CourseSelection(main_course=self.service, addons=self.addons)
