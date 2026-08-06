"""Contract tests for the booking gateway port and its immutable DTOs."""

from dataclasses import FrozenInstanceError
from datetime import date, time
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

import pytest

from app.domain.booking_models import (
    AvailabilityRequest,
    Booking,
    BookingGateway,
    ChildReservationReference,
    Course,
    CourseSearchRequest,
    CreateBookingRequest,
    CreateBookingResult,
    Customer,
    CustomerVerificationRequest,
    CustomerVerificationResult,
    FinalAvailabilityRequest,
    FinalAvailabilityResult,
    InvalidBookingDataError,
    InvalidCourseSelectionError,
    InvalidCustomerCountError,
    InvalidDurationError,
    Shop,
    TherapistPreference,
    TherapistPreferenceType,
)

SHOP_ID = UUID("11111111-1111-1111-1111-111111111111")
SERVICE_ID = UUID("22222222-2222-2222-2222-222222222222")
ADDON_ID = UUID("33333333-3333-3333-3333-333333333333")
BOOKING_ID = UUID("44444444-4444-4444-4444-444444444444")
RESERVATION_ID = UUID("55555555-5555-5555-5555-555555555555")
BOOKING_DATE = date(2026, 8, 1)
START_TIME = time(10, 30)
SHOP = Shop(shop_id=SHOP_ID, name="Central Spa")
COURSE = Course(
    course_id=SERVICE_ID,
    name="Aromatherapy",
    duration_minutes=60,
    price=Decimal("500000.00"),
)
CUSTOMER = Customer(phone="0901234567", name="Nguyen An")
BOOKING = Booking(
    booking_id=BOOKING_ID,
    status="confirmed",
    shop=SHOP,
    main_course=COURSE,
    customer=CUSTOMER,
    booking_date=BOOKING_DATE,
    start_time=START_TIME,
    reservation_code="RSV-001",
)
AVAILABILITY_REQUEST = AvailabilityRequest(
    shop_id=SHOP_ID,
    booking_date=BOOKING_DATE,
    num_customer=1,
    duration_minutes=60,
    main_course_id=SERVICE_ID,
    addon_ids=(ADDON_ID,),
)
FINAL_REQUEST = FinalAvailabilityRequest(
    shop_id=SHOP_ID,
    booking_date=BOOKING_DATE,
    start_time=START_TIME,
    num_customer=1,
    duration_minutes=60,
    main_course_id=SERVICE_ID,
    addon_ids=(ADDON_ID,),
)
CREATE_REQUEST = CreateBookingRequest(
    shop_id=SHOP_ID,
    booking_date=BOOKING_DATE,
    start_time=START_TIME,
    num_customer=1,
    duration_minutes=60,
    main_course_id=SERVICE_ID,
    addon_ids=(ADDON_ID,),
    therapist_preference=None,
    phone=CUSTOMER.phone,
    idempotency_key="conversation-1:attempt-1",
)
COURSE_REQUEST = CourseSearchRequest(shop_id=SHOP_ID)
CUSTOMER_REQUEST = CustomerVerificationRequest(
    shop_id=SHOP_ID,
    phone=CUSTOMER.phone,
)


class FakeBookingGateway:
    """In-memory fake implementing every booking gateway operation."""

    def __init__(self) -> None:
        self.availability_requests: list[AvailabilityRequest] = []
        self.customer_verification_requests: list[CustomerVerificationRequest] = []
        self.final_availability_requests: list[FinalAvailabilityRequest] = []
        self.create_booking_requests: list[CreateBookingRequest] = []

    async def search_shops(self, query: str | None = None) -> list[Shop]:
        return [SHOP]

    async def search_courses(
        self,
        request: CourseSearchRequest,
    ) -> list[Course]:
        return [COURSE]

    async def get_available_slots(
        self,
        request: AvailabilityRequest,
    ) -> tuple[time, ...]:
        self.availability_requests.append(request)
        return (START_TIME,)

    async def verify_customer(
        self,
        request: CustomerVerificationRequest,
    ) -> CustomerVerificationResult:
        self.customer_verification_requests.append(request)
        return CustomerVerificationResult(
            request.phone,
            "customer-1",
            "gold",
            3,
            True,
            False,
        )

    async def check_final_availability(
        self,
        request: FinalAvailabilityRequest,
    ) -> FinalAvailabilityResult:
        self.final_availability_requests.append(request)
        return FinalAvailabilityResult(available=True)

    async def create_booking(
        self,
        request: CreateBookingRequest,
    ) -> CreateBookingResult:
        self.create_booking_requests.append(request)
        return CreateBookingResult(BOOKING, reservation_code="RSV-001")

    async def lookup_booking(self, booking_id: UUID) -> Booking:
        return BOOKING

    async def reschedule_booking(
        self,
        booking_id: UUID,
        booking_date: date,
        start_time: time,
    ) -> Booking:
        return BOOKING

    async def cancel_booking(self, booking_id: UUID) -> Booking:
        return BOOKING


class IncompleteBookingGateway:
    """Fake that intentionally does not satisfy the gateway protocol."""


if TYPE_CHECKING:
    valid_gateway: BookingGateway = FakeBookingGateway()
    invalid_gateway: BookingGateway = IncompleteBookingGateway()  # type: ignore[assignment]


def test_dtos_are_immutable() -> None:
    with pytest.raises(FrozenInstanceError):
        AVAILABILITY_REQUEST.num_customer = 2  # type: ignore[misc]

    with pytest.raises(FrozenInstanceError):
        CUSTOMER_REQUEST.phone = "0912345678"  # type: ignore[misc]

    child = ChildReservationReference(RESERVATION_ID, participant_index=1)
    with pytest.raises(FrozenInstanceError):
        child.participant_index = 2  # type: ignore[misc]


def test_customer_verification_request_requires_phone() -> None:
    with pytest.raises(InvalidBookingDataError, match="phone"):
        CustomerVerificationRequest(shop_id=SHOP_ID, phone="")


@pytest.mark.parametrize("num_customer", [0, -1, 4])
def test_availability_request_rejects_invalid_customer_count(
    num_customer: int,
) -> None:
    with pytest.raises(InvalidCustomerCountError):
        AvailabilityRequest(
            SHOP_ID,
            BOOKING_DATE,
            num_customer,
            60,
            SERVICE_ID,
        )


@pytest.mark.parametrize("duration_minutes", [0, 20, 50])
def test_availability_request_rejects_invalid_duration(
    duration_minutes: int,
) -> None:
    with pytest.raises(InvalidDurationError):
        AvailabilityRequest(
            SHOP_ID,
            BOOKING_DATE,
            1,
            duration_minutes,
            SERVICE_ID,
        )


def test_availability_request_rejects_duplicate_course_ids() -> None:
    with pytest.raises(InvalidCourseSelectionError):
        AvailabilityRequest(
            SHOP_ID,
            BOOKING_DATE,
            1,
            60,
            SERVICE_ID,
            (ADDON_ID, ADDON_ID),
        )


def test_availability_request_accepts_group_gender_preference() -> None:
    request = AvailabilityRequest(
        SHOP_ID,
        BOOKING_DATE,
        2,
        60,
        SERVICE_ID,
        therapist_preference=TherapistPreference(TherapistPreferenceType.FEMALE),
    )

    assert request.therapist_preference == TherapistPreference(
        TherapistPreferenceType.FEMALE
    )


def test_create_result_rejects_duplicate_reservation_codes() -> None:
    with pytest.raises(ValueError, match="unique"):
        CreateBookingResult(
            BOOKING,
            reservation_code="RSV-001",
            reservation_codes=("RSV-001",),
        )


def test_create_result_preserves_child_reservations() -> None:
    child = ChildReservationReference(RESERVATION_ID, participant_index=1)

    result = CreateBookingResult(BOOKING, child_reservations=(child,))

    assert result.child_reservations == (child,)


def test_create_result_rejects_duplicate_child_reservation_ids() -> None:
    first = ChildReservationReference(RESERVATION_ID, participant_index=1)
    duplicate = ChildReservationReference(RESERVATION_ID, participant_index=2)

    with pytest.raises(ValueError, match="Child reservation IDs"):
        CreateBookingResult(BOOKING, child_reservations=(first, duplicate))


@pytest.mark.asyncio
async def test_fake_gateway_supports_complete_contract_and_records_dtos() -> None:
    gateway: BookingGateway = FakeBookingGateway()

    courses = await gateway.search_courses(COURSE_REQUEST)
    slots = await gateway.get_available_slots(AVAILABILITY_REQUEST)
    verification = await gateway.verify_customer(CUSTOMER_REQUEST)
    final = await gateway.check_final_availability(FINAL_REQUEST)
    created = await gateway.create_booking(CREATE_REQUEST)
    found = await gateway.lookup_booking(BOOKING_ID)
    rescheduled = await gateway.reschedule_booking(
        BOOKING_ID,
        BOOKING_DATE,
        START_TIME,
    )
    cancelled = await gateway.cancel_booking(BOOKING_ID)

    assert courses == [COURSE]
    assert slots == (START_TIME,)
    assert verification.member_rank == "gold"
    assert final.available is True
    assert created.booking is BOOKING
    assert found is BOOKING
    assert rescheduled is BOOKING
    assert cancelled is BOOKING
