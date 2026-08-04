"""Tests for mapping a booking context to an availability request."""

from datetime import date, time
from decimal import Decimal
from uuid import UUID

import pytest

from app.application.exceptions import SlotConflictError
from app.application.handlers.check_availability_handler import (
    CheckAvailabilityHandler,
)
from app.application.ports.booking_gateway import (
    AvailabilityRequest,
    BookingGateway,
    CourseSearchRequest,
    CreateBookingRequest,
    CreateBookingResult,
    CustomerVerificationRequest,
    CustomerVerificationResult,
    FinalAvailabilityRequest,
    FinalAvailabilityResult,
)
from app.domain.booking import (
    Booking,
    CourseType,
    Service,
    Shop,
    TherapistPreference,
    TherapistPreferenceType,
)
from app.domain.booking_context import BookingContext
from app.domain.booking_state import BookingState
from app.domain.exceptions import (
    BookingContextNotReadyError,
    InvalidBookingDataError,
    InvalidCourseSelectionError,
    TherapistNotAllowedForGroupError,
)

SHOP_ID = UUID("11111111-1111-1111-1111-111111111111")
MAIN_ID = UUID("22222222-2222-2222-2222-222222222222")
ADDON_ID = UUID("33333333-3333-3333-3333-333333333333")
BOOKING_DATE = date(2026, 8, 1)
MAIN = Service(MAIN_ID, "Aromatherapy", 60, Decimal("500000.00"))
ADDON = Service(
    ADDON_ID,
    "Essential oil",
    15,
    Decimal("100000.00"),
    CourseType.ADDON,
)
SHOP = Shop(SHOP_ID, "Central Spa")
SLOTS = (time(10, 30), time(11, 0))


class FakeBookingGateway:
    """Fake that records the exact availability request."""

    def __init__(
        self,
        slots: tuple[time, ...] = SLOTS,
        error: Exception | None = None,
    ) -> None:
        self.slots = slots
        self.error = error
        self.availability_requests: list[AvailabilityRequest] = []
        self.customer_verification_requests: list[CustomerVerificationRequest] = []
        self.final_availability_requests: list[FinalAvailabilityRequest] = []
        self.create_booking_requests: list[CreateBookingRequest] = []

    async def search_shops(self, query: str | None = None) -> list[Shop]:
        raise AssertionError("Unexpected search_shops call.")

    async def search_services(
        self,
        request: CourseSearchRequest,
    ) -> list[Service]:
        raise AssertionError("Unexpected search_services call.")

    async def get_available_slots(
        self,
        request: AvailabilityRequest,
    ) -> tuple[time, ...]:
        self.availability_requests.append(request)
        if self.error is not None:
            raise self.error
        return self.slots

    async def verify_customer(
        self,
        request: CustomerVerificationRequest,
    ) -> CustomerVerificationResult:
        raise AssertionError("Unexpected verify_customer call.")

    async def check_final_availability(
        self,
        request: FinalAvailabilityRequest,
    ) -> FinalAvailabilityResult:
        raise AssertionError("Unexpected final availability call.")

    async def create_booking(
        self,
        request: CreateBookingRequest,
    ) -> CreateBookingResult:
        raise AssertionError("Unexpected create_booking call.")

    async def lookup_booking(self, booking_id: UUID) -> Booking:
        raise AssertionError("Unexpected lookup_booking call.")

    async def reschedule_booking(
        self,
        booking_id: UUID,
        booking_date: date,
        start_time: time,
    ) -> Booking:
        raise AssertionError("Unexpected reschedule_booking call.")

    async def cancel_booking(self, booking_id: UUID) -> Booking:
        raise AssertionError("Unexpected cancel_booking call.")


def make_context(
    *,
    num_customer: int = 1,
    therapist: TherapistPreference | None = None,
) -> BookingContext:
    return BookingContext(
        conversation_id="conversation-1",
        state=BookingState.SELECTING_TIME,
        shop=SHOP,
        service=MAIN,
        addons=(ADDON,),
        booking_date=BOOKING_DATE,
        num_customer=num_customer,
        duration_minutes=60,
        therapist_preference=therapist,
    )


def make_handler(fake: FakeBookingGateway) -> CheckAvailabilityHandler:
    gateway: BookingGateway = fake
    return CheckAvailabilityHandler(gateway)


@pytest.mark.asyncio
async def test_execute_maps_complete_request_and_updates_slots_only() -> None:
    preference = TherapistPreference(TherapistPreferenceType.FEMALE)
    context = make_context(therapist=preference)
    original_state = context.state
    fake = FakeBookingGateway()

    result = await make_handler(fake).execute(context)

    assert fake.availability_requests == [
        AvailabilityRequest(
            shop_id=SHOP_ID,
            booking_date=BOOKING_DATE,
            num_customer=1,
            duration_minutes=75,
            main_course_id=MAIN_ID,
            addon_ids=(ADDON_ID,),
            therapist_preference=preference,
        )
    ]
    assert result is SLOTS
    assert context.available_slots is SLOTS
    assert context.start_time is None
    assert context.state is original_state


@pytest.mark.asyncio
async def test_empty_availability_is_a_typed_conflict_and_stores_no_slots() -> None:
    context = make_context()
    fake = FakeBookingGateway(slots=())

    with pytest.raises(SlotConflictError):
        await make_handler(fake).execute(context)

    assert context.available_slots == ()
    assert context.start_time is None
    assert len(fake.availability_requests) == 1


@pytest.mark.parametrize("group_size", [2, 3])
@pytest.mark.asyncio
async def test_group_request_has_no_specified_therapist(group_size: int) -> None:
    context = make_context(num_customer=group_size)
    fake = FakeBookingGateway()

    await make_handler(fake).execute(context)

    assert fake.availability_requests[0].therapist_preference is None


@pytest.mark.asyncio
async def test_group_with_specified_therapist_is_rejected_before_gateway() -> None:
    context = make_context(
        num_customer=2,
        therapist=TherapistPreference(TherapistPreferenceType.FEMALE),
    )
    fake = FakeBookingGateway()

    with pytest.raises(TherapistNotAllowedForGroupError):
        await make_handler(fake).execute(context)

    assert fake.availability_requests == []


@pytest.mark.parametrize("missing_field", ["booking_date", "service"])
@pytest.mark.asyncio
async def test_missing_context_data_is_rejected_before_gateway(
    missing_field: str,
) -> None:
    context = make_context()
    setattr(context, missing_field, None)
    fake = FakeBookingGateway()

    with pytest.raises(BookingContextNotReadyError):
        await make_handler(fake).execute(context)

    assert fake.availability_requests == []


@pytest.mark.asyncio
async def test_addon_cannot_be_used_as_main_course() -> None:
    context = make_context()
    context.service = ADDON
    context.addons = ()
    fake = FakeBookingGateway()

    with pytest.raises(InvalidCourseSelectionError):
        await make_handler(fake).execute(context)

    assert fake.availability_requests == []


@pytest.mark.asyncio
async def test_gateway_error_does_not_mutate_existing_slots_or_state() -> None:
    error = InvalidBookingDataError("POS unavailable.")
    context = make_context()
    old_slots = (time(9, 0),)
    context.available_slots = old_slots
    original_state = context.state
    fake = FakeBookingGateway(error=error)

    with pytest.raises(InvalidBookingDataError) as exc_info:
        await make_handler(fake).execute(context)

    assert exc_info.value is error
    assert context.available_slots is old_slots
    assert context.state is original_state
