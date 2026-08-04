"""Tests for customer collection and authoritative POS verification."""

from datetime import date, time
from uuid import UUID

import pytest

from app.application.exceptions import CustomerVerificationMismatchError
from app.application.handlers.collect_customer_handler import CollectCustomerHandler
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
from app.domain.booking import Booking, Service, Shop
from app.domain.booking_context import BookingContext
from app.domain.booking_state import BookingState
from app.domain.exceptions import CustomerNotAllowedError, InvalidBookingDataError

SHOP = Shop(UUID("11111111-1111-1111-1111-111111111111"), "Central Spa")
OTHER_SHOP = Shop(UUID("22222222-2222-2222-2222-222222222222"), "Riverside Spa")


class FakeBookingGateway:
    """Fake that records verification calls and returns a configured result."""

    def __init__(
        self,
        result: CustomerVerificationResult,
        error: Exception | None = None,
    ) -> None:
        self.result = result
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
        raise AssertionError("Unexpected get_available_slots call.")

    async def verify_customer(
        self,
        request: CustomerVerificationRequest,
    ) -> CustomerVerificationResult:
        self.customer_verification_requests.append(request)
        if self.error is not None:
            raise self.error
        return self.result

    async def check_final_availability(
        self,
        request: FinalAvailabilityRequest,
    ) -> FinalAvailabilityResult:
        raise AssertionError("Unexpected check_final_availability call.")

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


def verification(
    *,
    phone: str = "0901234567",
    member_rank: str | None = "gold",
    checked: bool = True,
    is_ng: bool = False,
) -> CustomerVerificationResult:
    return CustomerVerificationResult(
        phone=phone,
        customer_id="customer-1",
        member_rank=member_rank,
        visit_count=4,
        ng_list_checked=checked,
        is_ng_customer=is_ng,
    )


def make_handler(fake: FakeBookingGateway) -> CollectCustomerHandler:
    gateway: BookingGateway = fake
    return CollectCustomerHandler(gateway)


@pytest.mark.asyncio
async def test_execute_normalizes_phone_and_stores_customer_verification() -> None:
    context = BookingContext(
        conversation_id="conversation-1",
        state=BookingState.COLLECTING_PHONE,
        shop=SHOP,
    )
    fake = FakeBookingGateway(verification())
    original_state = context.state

    result = await make_handler(fake).execute(
        context,
        "090-123-4567",
        "  Nguyen An  ",
    )

    assert result is fake.result
    assert fake.customer_verification_requests == [
        CustomerVerificationRequest(shop_id=SHOP.shop_id, phone="0901234567")
    ]
    assert context.phone == "0901234567"
    assert context.customer is not None
    assert context.customer.phone == "0901234567"
    assert context.customer.name == "Nguyen An"
    assert context.member_rank == "gold"
    assert context.visit_count == 4
    assert context.ng_list_checked is True
    assert context.is_ng_customer is False
    assert context.phone_confirmed is False
    assert context.state is original_state


@pytest.mark.asyncio
async def test_existing_customer_uses_pos_name_while_new_customer_waits_for_name() -> None:
    existing_context = BookingContext("existing", shop=SHOP)
    existing = verification()
    existing = CustomerVerificationResult(
        phone=existing.phone,
        customer_id=existing.customer_id,
        member_rank=existing.member_rank,
        visit_count=existing.visit_count,
        ng_list_checked=existing.ng_list_checked,
        is_ng_customer=existing.is_ng_customer,
        customer_name="POS Customer",
    )
    await make_handler(FakeBookingGateway(existing)).execute(
        existing_context,
        existing.phone,
    )

    new_context = BookingContext("new", shop=SHOP)
    new_customer = CustomerVerificationResult(
        phone="0912345678",
        customer_id=None,
        member_rank=None,
        visit_count=None,
        ng_list_checked=True,
        is_ng_customer=False,
    )
    await make_handler(FakeBookingGateway(new_customer)).execute(
        new_context,
        new_customer.phone,
    )

    assert existing_context.customer_id == "customer-1"
    assert existing_context.customer is not None
    assert existing_context.customer.name == "POS Customer"
    assert new_context.customer_id is None
    assert new_context.customer is not None
    assert new_context.customer.name is None


@pytest.mark.asyncio
async def test_invalid_phone_does_not_call_gateway_or_mutate_context() -> None:
    context = BookingContext(
        conversation_id="conversation-1",
        shop=SHOP,
        phone="0901234567",
        phone_confirmed=True,
        member_rank="silver",
        ng_list_checked=True,
    )
    fake = FakeBookingGateway(verification())

    with pytest.raises(InvalidBookingDataError):
        await make_handler(fake).execute(context, "invalid-phone")

    assert fake.customer_verification_requests == []
    assert context.phone == "0901234567"
    assert context.phone_confirmed is True
    assert context.member_rank == "silver"
    assert context.ng_list_checked is True


@pytest.mark.asyncio
async def test_new_phone_resets_old_verification_before_gateway_failure() -> None:
    error = RuntimeError("POS unavailable")
    context = BookingContext(
        conversation_id="conversation-1",
        shop=SHOP,
        phone="0901234567",
        phone_confirmed=True,
        member_rank="gold",
        visit_count=9,
        ng_list_checked=True,
        is_ng_customer=True,
    )
    fake = FakeBookingGateway(verification(), error=error)

    with pytest.raises(RuntimeError) as exc_info:
        await make_handler(fake).execute(context, "0912345678")

    assert exc_info.value is error
    assert fake.customer_verification_requests == [
        CustomerVerificationRequest(shop_id=SHOP.shop_id, phone="0912345678")
    ]
    assert context.phone == "0912345678"
    assert context.phone_confirmed is False
    assert context.member_rank is None
    assert context.visit_count is None
    assert context.ng_list_checked is False
    assert context.is_ng_customer is False
    assert context.customer is None


@pytest.mark.asyncio
async def test_ng_customer_result_is_stored_and_context_remains_not_ready() -> None:
    context = BookingContext(conversation_id="conversation-1", shop=SHOP)
    fake = FakeBookingGateway(verification(is_ng=True))

    await make_handler(fake).execute(context, "0901234567")

    assert context.ng_list_checked is True
    assert context.is_ng_customer is True
    assert context.phone_confirmed is False
    assert context.is_ready_to_create() is False


@pytest.mark.asyncio
async def test_authoritative_ng_error_is_stored_and_propagated() -> None:
    error = CustomerNotAllowedError("NG customer")
    context = BookingContext(conversation_id="conversation-1", shop=SHOP)
    fake = FakeBookingGateway(verification(), error=error)

    with pytest.raises(CustomerNotAllowedError) as captured:
        await make_handler(fake).execute(context, "0901234567", "Nguyen An")

    assert captured.value is error
    assert context.customer is not None
    assert context.customer.phone == "0901234567"
    assert context.ng_list_checked is True
    assert context.is_ng_customer is True
    assert context.phone_confirmed is False
    assert context.is_ready_to_create() is False


@pytest.mark.asyncio
async def test_unchecked_ng_result_remains_unverified() -> None:
    context = BookingContext(conversation_id="conversation-1", shop=SHOP)
    fake = FakeBookingGateway(verification(checked=False))

    await make_handler(fake).execute(context, "0901234567")

    assert context.member_rank == "gold"
    assert context.ng_list_checked is False
    assert context.is_ready_to_create() is False


@pytest.mark.asyncio
async def test_response_phone_mismatch_is_rejected_without_verification() -> None:
    context = BookingContext(conversation_id="conversation-1", shop=SHOP)
    fake = FakeBookingGateway(verification(phone="0912345678"))

    with pytest.raises(CustomerVerificationMismatchError):
        await make_handler(fake).execute(context, "0901234567")

    assert context.phone == "0901234567"
    assert context.customer is None
    assert context.member_rank is None
    assert context.ng_list_checked is False
    assert context.phone_confirmed is False


@pytest.mark.asyncio
async def test_missing_shop_does_not_call_gateway_or_mutate_phone() -> None:
    context = BookingContext(conversation_id="conversation-1", phone="0901234567")
    fake = FakeBookingGateway(verification())

    with pytest.raises(InvalidBookingDataError, match="shop"):
        await make_handler(fake).execute(context, "0912345678")

    assert fake.customer_verification_requests == []
    assert context.phone == "0901234567"


@pytest.mark.asyncio
async def test_verification_uses_the_current_shop_after_shop_change() -> None:
    context = BookingContext(conversation_id="conversation-1", shop=SHOP)
    fake = FakeBookingGateway(verification())
    context.set_shop(OTHER_SHOP)

    await make_handler(fake).execute(context, "0901234567")

    assert fake.customer_verification_requests == [
        CustomerVerificationRequest(
            shop_id=OTHER_SHOP.shop_id,
            phone="0901234567",
        )
    ]
