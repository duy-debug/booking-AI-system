"""Tests for final-check-first idempotent booking creation."""

from datetime import date, time
from decimal import Decimal
from uuid import UUID

import pytest

from app.application.handlers.create_booking_handler import CreateBookingHandler
from app.domain.booking_context import BookingContext
from app.domain.booking_models import (
    AvailabilityRequest,
    AvailabilityWindowResult,
    Booking,
    BookingGateway,
    ChildReservationReference,
    Course,
    CourseSearchRequest,
    CourseType,
    CreateBookingRequest,
    CreateBookingResult,
    Customer,
    CustomerNotAllowedError,
    CustomerVerificationRequest,
    CustomerVerificationRequiredError,
    CustomerVerificationResult,
    FinalAvailabilityRequest,
    FinalAvailabilityResult,
    InvalidBookingDataError,
    InvalidIdempotencyKeyError,
    PhoneNotConfirmedError,
    Shop,
    SlotConflictError,
    TherapistPreference,
    TherapistPreferenceType,
)
from app.domain.booking_state import BookingState
from app.domain.outcomes import HandlerOutcome

SHOP_ID = UUID("11111111-1111-1111-1111-111111111111")
MAIN_ID = UUID("22222222-2222-2222-2222-222222222222")
ADDON_ID = UUID("33333333-3333-3333-3333-333333333333")
BOOKING_ID = UUID("44444444-4444-4444-4444-444444444444")
RESERVATION_ID = UUID("55555555-5555-5555-5555-555555555555")
BOOKING_DATE = date(2099, 8, 1)
START_TIME = time(10, 30)
SHOP = Shop(SHOP_ID, "Central Spa")
MAIN = Course(MAIN_ID, "Aromatherapy", 60, Decimal("500000.00"))
ADDON = Course(
    ADDON_ID,
    "Essential oil",
    15,
    Decimal("100000.00"),
    CourseType.ADDON,
)
CUSTOMER = Customer("0901234567", "Nguyen An")
BOOKING = Booking(
    booking_id=BOOKING_ID,
    status="confirmed",
    shop=SHOP,
    main_course=MAIN,
    customer=CUSTOMER,
    booking_date=BOOKING_DATE,
    start_time=START_TIME,
    duration_minutes=75,
    addons=(ADDON,),
    reservation_code="RSV-001",
)


class FakeBookingGateway:
    """Fake that records final-check and create ordering and payloads."""

    def __init__(
        self,
        *,
        final_result: FinalAvailabilityResult | None = None,
        create_result: CreateBookingResult | None = None,
        final_error: Exception | None = None,
        create_error: Exception | None = None,
    ) -> None:
        self.final_result = final_result or FinalAvailabilityResult(True)
        self.create_result = create_result or CreateBookingResult(
            BOOKING,
            reservation_code="RSV-001",
            reservation_codes=("RSV-CHILD-1",),
            child_reservations=(ChildReservationReference(RESERVATION_ID, participant_index=1),),
        )
        self.final_error = final_error
        self.create_error = create_error
        self.availability_requests: list[AvailabilityRequest] = []
        self.customer_verification_requests: list[CustomerVerificationRequest] = []
        self.final_availability_requests: list[FinalAvailabilityRequest] = []
        self.create_booking_requests: list[CreateBookingRequest] = []
        self.call_order: list[str] = []

    async def search_shops(self, query: str | None = None) -> list[Shop]:
        raise AssertionError("Unexpected search_shops call.")

    async def search_courses(
        self,
        request: CourseSearchRequest,
    ) -> list[Course]:
        raise AssertionError("Unexpected search_courses call.")

    async def get_available_slots(
        self,
        request: AvailabilityRequest,
    ) -> AvailabilityWindowResult:
        raise AssertionError("Unexpected get_available_slots call.")

    async def verify_customer(
        self,
        request: CustomerVerificationRequest,
    ) -> CustomerVerificationResult:
        raise AssertionError("Unexpected verify_customer call.")

    async def check_final_availability(
        self,
        request: FinalAvailabilityRequest,
    ) -> FinalAvailabilityResult:
        self.call_order.append("final")
        self.final_availability_requests.append(request)
        if self.final_error is not None:
            raise self.final_error
        return self.final_result

    async def create_booking(
        self,
        request: CreateBookingRequest,
    ) -> CreateBookingResult:
        self.call_order.append("create")
        self.create_booking_requests.append(request)
        if self.create_error is not None:
            raise self.create_error
        return self.create_result

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


def make_context() -> BookingContext:
    return BookingContext(
        conversation_id="conversation-1",
        state=BookingState.BOOKING_EXECUTING,
        shop=SHOP,
        main_course=MAIN,
        addons=(ADDON,),
        customer=CUSTOMER,
        booking_date=BOOKING_DATE,
        start_time=START_TIME,
        num_customer=1,
        duration_minutes=60,
        phone=CUSTOMER.phone,
        phone_confirmed=True,
        member_rank="gold",
        ng_list_checked=True,
        last_failure_code="create_booking",
    )


def make_handler(fake: FakeBookingGateway) -> CreateBookingHandler:
    gateway: BookingGateway = fake
    return CreateBookingHandler(gateway)


@pytest.mark.parametrize(
    ("field", "value", "exception_type"),
    [
        ("shop", None, InvalidBookingDataError),
        ("phone_confirmed", False, PhoneNotConfirmedError),
        ("ng_list_checked", False, CustomerVerificationRequiredError),
        ("is_ng_customer", True, CustomerNotAllowedError),
    ],
)
@pytest.mark.asyncio
async def test_unready_context_never_calls_gateway(
    field: str,
    value: object,
    exception_type: type[Exception],
) -> None:
    context = make_context()
    setattr(context, field, value)
    fake = FakeBookingGateway()

    with pytest.raises(exception_type):
        await make_handler(fake).execute(context, "attempt-1")

    assert fake.final_availability_requests == []
    assert fake.create_booking_requests == []


@pytest.mark.asyncio
async def test_group_with_gender_preference_reaches_gateway() -> None:
    context = make_context()
    context.num_customer = 2
    context.therapist_preference = TherapistPreference(TherapistPreferenceType.FEMALE)
    fake = FakeBookingGateway()

    await make_handler(fake).execute(context, "attempt-1")

    assert fake.final_availability_requests[0].therapist_preference == TherapistPreference(
        TherapistPreferenceType.FEMALE
    )
    assert fake.create_booking_requests[0].therapist_preference == TherapistPreference(
        TherapistPreferenceType.FEMALE
    )


@pytest.mark.parametrize("key", ["", "   "])
@pytest.mark.asyncio
async def test_empty_idempotency_key_is_rejected_before_gateway(key: str) -> None:
    fake = FakeBookingGateway()

    with pytest.raises(InvalidIdempotencyKeyError):
        await make_handler(fake).execute(make_context(), key)

    assert fake.call_order == []


@pytest.mark.asyncio
async def test_final_check_precedes_create_and_requests_are_complete() -> None:
    preference = TherapistPreference(TherapistPreferenceType.FEMALE)
    context = make_context()
    context.therapist_preference = preference
    original_state = context.state
    fake = FakeBookingGateway()

    result = await make_handler(fake).execute(context, "conversation-1:attempt-1")

    assert fake.call_order == ["final", "create"]
    assert fake.final_availability_requests == [
        FinalAvailabilityRequest(
            shop_id=SHOP_ID,
            booking_date=BOOKING_DATE,
            start_time=START_TIME,
            num_customer=1,
            duration_minutes=75,
            main_course_id=MAIN_ID,
            addon_ids=(ADDON_ID,),
            therapist_preference=preference,
        )
    ]
    assert fake.create_booking_requests == [
        CreateBookingRequest(
            shop_id=SHOP_ID,
            booking_date=BOOKING_DATE,
            start_time=START_TIME,
            num_customer=1,
            duration_minutes=75,
            main_course_id=MAIN_ID,
            addon_ids=(ADDON_ID,),
            therapist_preference=preference,
            phone=CUSTOMER.phone,
            idempotency_key="conversation-1:attempt-1",
            member_rank="gold",
            customer_name="Nguyen An",
        )
    ]
    assert result.outcome is HandlerOutcome.SUCCESS
    assert result.data["create_result"] is fake.create_result
    assert result.context_updates["booking"] is BOOKING
    assert result.context_updates["booking_id"] == BOOKING_ID
    assert result.context_updates["reservation_code"] == str(BOOKING_ID)
    assert context.booking is None
    assert context.state is original_state
    assert context.last_failure_code == "create_booking"


@pytest.mark.asyncio
async def test_unavailable_final_check_raises_conflict_with_nearest_slots() -> None:
    nearest = (time(11, 0), time(11, 30))
    context = make_context()
    original_values = (
        context.booking,
        context.booking_id,
        context.reservation_code,
    )
    fake = FakeBookingGateway(
        final_result=FinalAvailabilityResult(
            available=False,
            nearest_slots=nearest,
            reason="slot_conflict",
        )
    )

    with pytest.raises(SlotConflictError) as exc_info:
        await make_handler(fake).execute(context, "attempt-1")

    assert exc_info.value.nearest_slots == nearest
    assert exc_info.value.reason == "slot_conflict"
    assert fake.call_order == ["final"]
    assert fake.create_booking_requests == []
    assert (
        context.booking,
        context.booking_id,
        context.reservation_code,
    ) == original_values


@pytest.mark.asyncio
async def test_create_error_is_propagated_without_result_mutation_or_retry() -> None:
    error = RuntimeError("POS 5xx")
    context = make_context()
    original_state = context.state
    fake = FakeBookingGateway(create_error=error)

    with pytest.raises(RuntimeError) as exc_info:
        await make_handler(fake).execute(context, "attempt-1")

    assert exc_info.value is error
    assert fake.call_order == ["final", "create"]
    assert len(fake.create_booking_requests) == 1
    assert context.booking is None
    assert context.booking_id is None
    assert context.reservation_code is None
    assert context.state is original_state


@pytest.mark.asyncio
async def test_external_retry_reuses_the_same_idempotency_key() -> None:
    fake = FakeBookingGateway()
    handler = make_handler(fake)
    key = "conversation-1:stable-attempt"

    await handler.execute(make_context(), key)
    await handler.execute(make_context(), key)

    assert [request.idempotency_key for request in fake.create_booking_requests] == [
        key,
        key,
    ]
    assert fake.call_order == ["final", "create", "final", "create"]
