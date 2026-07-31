"""Contract tests for the booking gateway port and its immutable DTOs."""

from dataclasses import FrozenInstanceError
from datetime import date, time
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

import pytest

from app.application.ports.booking_gateway import (
    AvailabilityRequest,
    BookingGateway,
    CreateBookingRequest,
    CreateBookingResult,
    CustomerVerificationResult,
    FinalAvailabilityRequest,
    FinalAvailabilityResult,
)
from app.domain.booking import (
    Booking,
    Customer,
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

SHOP_ID = UUID("11111111-1111-1111-1111-111111111111")
SERVICE_ID = UUID("22222222-2222-2222-2222-222222222222")
ADDON_ID = UUID("33333333-3333-3333-3333-333333333333")
BOOKING_ID = UUID("44444444-4444-4444-4444-444444444444")
BOOKING_DATE = date(2026, 8, 1)
START_TIME = time(10, 30)
SHOP = Shop(shop_id=SHOP_ID, name="Central Spa")
SERVICE = Service(
    service_id=SERVICE_ID,
    name="Aromatherapy",
    duration_minutes=60,
    price=Decimal("500000.00"),
)
CUSTOMER = Customer(phone="0901234567", name="Nguyen An")
BOOKING = Booking(
    booking_id=BOOKING_ID,
    status="confirmed",
    shop=SHOP,
    service=SERVICE,
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


class FakeBookingGateway:
    """In-memory fake implementing every booking gateway operation."""

    def __init__(self) -> None:
        self.availability_requests: list[AvailabilityRequest] = []
        self.customer_verification_requests: list[str] = []
        self.final_availability_requests: list[FinalAvailabilityRequest] = []
        self.create_booking_requests: list[CreateBookingRequest] = []

    async def search_shops(self, query: str | None = None) -> list[Shop]:
        return [SHOP]

    async def search_services(
        self,
        shop_id: UUID,
        booking_date: date,
        query: str | None = None,
    ) -> list[Service]:
        return [SERVICE]

    async def get_available_slots(
        self,
        request: AvailabilityRequest,
    ) -> tuple[time, ...]:
        self.availability_requests.append(request)
        return (START_TIME,)

    async def verify_customer(self, phone: str) -> CustomerVerificationResult:
        self.customer_verification_requests.append(phone)
        return CustomerVerificationResult(phone, "customer-1", "gold", 3, True, False)

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


def test_availability_request_rejects_duplicate_service_ids() -> None:
    with pytest.raises(InvalidCourseSelectionError):
        AvailabilityRequest(
            SHOP_ID,
            BOOKING_DATE,
            1,
            60,
            SERVICE_ID,
            (ADDON_ID, ADDON_ID),
        )


def test_availability_request_rejects_group_therapist() -> None:
    with pytest.raises(TherapistNotAllowedForGroupError):
        AvailabilityRequest(
            SHOP_ID,
            BOOKING_DATE,
            2,
            60,
            SERVICE_ID,
            therapist_preference=TherapistPreference(
                TherapistPreferenceType.FEMALE
            ),
        )


def test_create_result_rejects_duplicate_reservation_codes() -> None:
    with pytest.raises(ValueError, match="unique"):
        CreateBookingResult(
            BOOKING,
            reservation_code="RSV-001",
            reservation_codes=("RSV-001",),
        )


@pytest.mark.asyncio
async def test_fake_gateway_supports_complete_contract_and_records_dtos() -> None:
    gateway: BookingGateway = FakeBookingGateway()

    services = await gateway.search_services(SHOP_ID, BOOKING_DATE, query="aroma")
    slots = await gateway.get_available_slots(AVAILABILITY_REQUEST)
    verification = await gateway.verify_customer(CUSTOMER.phone)
    final = await gateway.check_final_availability(FINAL_REQUEST)
    created = await gateway.create_booking(CREATE_REQUEST)
    found = await gateway.lookup_booking(BOOKING_ID)
    rescheduled = await gateway.reschedule_booking(
        BOOKING_ID,
        BOOKING_DATE,
        START_TIME,
    )
    cancelled = await gateway.cancel_booking(BOOKING_ID)

    assert services == [SERVICE]
    assert slots == (START_TIME,)
    assert verification.member_rank == "gold"
    assert final.available is True
    assert created.booking is BOOKING
    assert found is BOOKING
    assert rescheduled is BOOKING
    assert cancelled is BOOKING
