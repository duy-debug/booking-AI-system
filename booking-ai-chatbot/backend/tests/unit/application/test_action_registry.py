"""Tests for the application action registry and executor."""

from collections.abc import Mapping
from datetime import date, time
from decimal import Decimal
from typing import cast
from uuid import UUID

import pytest

from app.application.action_registry import (
    ActionCallable,
    ActionExecutionContext,
    ActionExecutionError,
    ActionRegistry,
    ActionResult,
    DuplicateActionError,
    FailureDescriptor,
    InvalidActionInputError,
    InvalidActionNameError,
    InvalidActionSequenceError,
    UnknownActionError,
)
from app.application.handlers.check_availability_handler import (
    CheckAvailabilityHandler,
)
from app.application.handlers.check_customer_handler import CheckCustomerHandler
from app.application.handlers.create_booking_handler import CreateBookingHandler
from app.application.handlers.search_shop_handler import SearchShopHandler
from app.dialog.flow_loader import FlowFailure, InvalidFlowConditionError
from app.domain.booking_context import BookingContext
from app.domain.booking_models import (
    AvailableTherapistRequest,
    Booking,
    BookingContextNotReadyError,
    BookingGateway,
    Course,
    CreateBookingResult,
    Customer,
    CustomerNotAllowedError,
    CustomerVerificationMismatchError,
    CustomerVerificationResult,
    InvalidBookingDataError,
    Shop,
    SlotConflictError,
    TherapistAvailabilityGateway,
    TherapistPreference,
    TherapistPreferenceType,
)
from app.domain.booking_state import BookingState
from app.domain.outcomes import HandlerOutcome, HandlerResult

SHOP = Shop(
    UUID("11111111-1111-1111-1111-111111111111"),
    "Central Spa",
)
COURSE = Course(
    UUID("22222222-2222-2222-2222-222222222222"),
    "Aromatherapy",
    60,
    Decimal("500000.00"),
)
CUSTOMER = Customer("0901234567", "Nguyen An")
BOOKING = Booking(
    booking_id=UUID("33333333-3333-3333-3333-333333333333"),
    status="confirmed",
    shop=SHOP,
    main_course=COURSE,
    customer=CUSTOMER,
    booking_date=date(2099, 8, 1),
    start_time=time(10, 30),
)


def execution_context(
    *,
    booking_context: BookingContext | None = None,
    payload: Mapping[str, object] | None = None,
    idempotency_key: str | None = None,
) -> ActionExecutionContext:
    return ActionExecutionContext(
        booking_context=booking_context or BookingContext(conversation_id="conversation-1"),
        intent="test_intent",
        payload=payload or {},
        idempotency_key=idempotency_key,
    )


async def successful_action(context: ActionExecutionContext) -> ActionResult:
    """Return a deterministic result for registry tests."""
    return ActionResult("custom_action", context.intent)


def test_register_lookup_order_and_instance_isolation() -> None:
    first = ActionRegistry()
    second = ActionRegistry()
    initial_names = first.registered_actions()

    first.register_action("custom_action", successful_action)

    assert first.has_action("custom_action") is True
    assert first.get_action("custom_action") is successful_action
    assert first.registered_actions() == initial_names + ("custom_action",)
    assert second.has_action("custom_action") is False


def test_duplicate_action_is_rejected_without_override() -> None:
    bridge = ActionRegistry()
    bridge.register_action("custom_action", successful_action)

    with pytest.raises(DuplicateActionError):
        bridge.register_action("custom_action", successful_action)

    assert bridge.get_action("custom_action") is successful_action


def test_unknown_action_is_rejected() -> None:
    with pytest.raises(UnknownActionError):
        ActionRegistry().get_action("missing_action")


@pytest.mark.asyncio
async def test_unknown_executed_action_is_wrapped_for_failure_mapping() -> None:
    bridge = ActionRegistry()

    with pytest.raises(ActionExecutionError) as exc_info:
        await bridge.execute_actions(("missing_action",), execution_context())

    assert isinstance(exc_info.value.__cause__, UnknownActionError)
    assert bridge.get_failure_code(exc_info.value) == "unknown_action_error"


@pytest.mark.parametrize(
    "name",
    ["", "   ", "Uppercase", "has-hyphen", "_private", "1starts_with_number"],
)
def test_invalid_action_names_are_rejected(name: str) -> None:
    with pytest.raises(InvalidActionNameError):
        ActionRegistry().register_action(name, successful_action)


def test_non_callable_action_is_rejected() -> None:
    with pytest.raises(TypeError):
        ActionRegistry().register_action(
            "not_callable",
            cast(ActionCallable, object()),
        )


@pytest.mark.asyncio
async def test_custom_async_action_can_be_executed() -> None:
    bridge = ActionRegistry()
    bridge.register_action("custom_action", successful_action)

    result = await bridge.execute_action("custom_action", execution_context())

    assert result == ActionResult("custom_action", "test_intent")


@pytest.mark.asyncio
async def test_actions_execute_sequentially_in_declared_order() -> None:
    calls: list[str] = []
    bridge = ActionRegistry()

    def action(name: str) -> ActionCallable:
        async def execute(context: ActionExecutionContext) -> ActionResult:
            calls.append(name)
            return ActionResult(name)

        return execute

    for name in ("first", "second", "third"):
        bridge.register_action(name, action(name))

    report = await bridge.execute_actions(
        ("first", "second", "third"),
        execution_context(),
    )

    assert calls == ["first", "second", "third"]
    assert report.succeeded is True
    assert report.executed_action_names == ("first", "second", "third")


@pytest.mark.asyncio
async def test_empty_action_sequence_returns_empty_success_report() -> None:
    report = await ActionRegistry().execute_actions((), execution_context())

    assert report.succeeded is True
    assert report.results == ()
    assert report.executed_action_names == ()


@pytest.mark.asyncio
async def test_failure_stops_sequence_chains_cause_and_rolls_back() -> None:
    calls: list[str] = []
    original_error = RuntimeError("second failed")
    booking_context = BookingContext(
        conversation_id="conversation-1",
        state=BookingState.SELECTING_PEOPLE,
        phone="old-phone",
    )
    identity = id(booking_context)
    bridge = ActionRegistry()

    async def first(context: ActionExecutionContext) -> ActionResult:
        calls.append("first")
        context.booking_context.phone = "new-phone"
        return ActionResult("first")

    async def second(context: ActionExecutionContext) -> ActionResult:
        calls.append("second")
        context.booking_context.num_customer = 2
        raise original_error

    async def third(context: ActionExecutionContext) -> ActionResult:
        calls.append("third")
        return ActionResult("third")

    bridge.register_action("first", first)
    bridge.register_action("second", second)
    bridge.register_action("third", third)

    with pytest.raises(ActionExecutionError) as exc_info:
        await bridge.execute_actions(
            ("first", "second", "third"),
            execution_context(booking_context=booking_context),
        )

    assert calls == ["first", "second"]
    assert exc_info.value.action_name == "second"
    assert exc_info.value.executed_actions == ("first",)
    assert exc_info.value.__cause__ is original_error
    assert id(booking_context) == identity
    assert booking_context.phone == "old-phone"
    assert booking_context.num_customer is None
    assert booking_context.state is BookingState.SELECTING_PEOPLE


@pytest.mark.asyncio
async def test_successful_mutations_are_kept_without_state_commit() -> None:
    booking_context = BookingContext(
        conversation_id="conversation-1",
        state=BookingState.SELECTING_PEOPLE,
    )
    bridge = ActionRegistry()

    await bridge.execute_action(
        "handle_people_selection",
        execution_context(
            booking_context=booking_context,
            payload={"num_customer": 2},
        ),
    )

    assert booking_context.num_customer == 2
    assert booking_context.state is BookingState.SELECTING_PEOPLE


@pytest.mark.asyncio
async def test_invalid_action_result_is_wrapped_and_rolled_back() -> None:
    booking_context = BookingContext(conversation_id="conversation-1")
    bridge = ActionRegistry()

    async def invalid_result(context: ActionExecutionContext) -> ActionResult:
        context.booking_context.phone = "mutated"
        return cast(ActionResult, object())

    bridge.register_action("invalid_result", invalid_result)

    with pytest.raises(ActionExecutionError) as exc_info:
        await bridge.execute_action(
            "invalid_result",
            execution_context(booking_context=booking_context),
        )

    assert isinstance(exc_info.value.__cause__, TypeError)
    assert booking_context.phone is None


@pytest.mark.parametrize(
    "action_names",
    [
        ("create_booking", "after"),
        ("create_booking", "create_booking"),
    ],
)
@pytest.mark.asyncio
async def test_unsafe_side_effect_sequence_is_rejected_before_execution(
    action_names: tuple[str, ...],
) -> None:
    calls: list[str] = []
    bridge = ActionRegistry()

    async def after(context: ActionExecutionContext) -> ActionResult:
        calls.append("after")
        return ActionResult("after")

    bridge.register_action("after", after)

    with pytest.raises(InvalidActionSequenceError):
        await bridge.execute_actions(
            action_names,
            execution_context(idempotency_key="stable-key"),
        )

    assert calls == []


@pytest.mark.asyncio
async def test_side_effect_at_end_is_allowed_and_not_retried() -> None:
    calls: list[str] = []
    bridge = ActionRegistry()

    async def first(context: ActionExecutionContext) -> ActionResult:
        calls.append("first")
        return ActionResult("first")

    async def create(context: ActionExecutionContext) -> ActionResult:
        calls.append("create_booking")
        return ActionResult("create_booking", context.idempotency_key)

    bridge.register_action("first", first)
    bridge.register_action("create_booking", create)

    report = await bridge.execute_actions(
        ("first", "create_booking"),
        execution_context(idempotency_key="stable-key"),
    )

    assert calls == ["first", "create_booking"]
    assert report.results[-1].output == "stable-key"


@pytest.mark.asyncio
async def test_side_effect_requires_idempotency_key_before_execution() -> None:
    calls: list[str] = []
    bridge = ActionRegistry()

    async def create(context: ActionExecutionContext) -> ActionResult:
        calls.append("create_booking")
        return ActionResult("create_booking")

    bridge.register_action("create_booking", create)

    with pytest.raises(InvalidActionInputError):
        await bridge.execute_actions(
            ("create_booking",),
            execution_context(),
        )

    assert calls == []


@pytest.mark.asyncio
async def test_failing_create_is_called_once_without_automatic_retry() -> None:
    calls = 0
    bridge = ActionRegistry()

    async def create(context: ActionExecutionContext) -> ActionResult:
        nonlocal calls
        calls += 1
        raise RuntimeError("POS unavailable")

    bridge.register_action("create_booking", create)

    with pytest.raises(ActionExecutionError):
        await bridge.execute_actions(
            ("create_booking",),
            execution_context(idempotency_key="stable-key"),
        )

    assert calls == 1


class FakeCheckAvailabilityHandler(CheckAvailabilityHandler):
    """Fake application handler that records availability execution."""

    def __init__(self, *, error: Exception | None = None) -> None:
        self.contexts: list[BookingContext] = []
        self.slots = (time(10, 30), time(11, 0))
        self.error = error

    async def execute(self, context: BookingContext) -> HandlerResult:
        self.contexts.append(context)
        if self.error is not None:
            raise self.error
        return HandlerResult(
            HandlerOutcome.SUCCESS,
            {"slots": self.slots},
            {"available_slots": self.slots},
        )


class FakeSearchShopHandler(SearchShopHandler):
    """Fake application handler that records default shop searches."""

    def __init__(self, *, error: Exception | None = None) -> None:
        self.calls: list[str | None] = []
        self.shops = [SHOP]
        self.error = error

    async def execute(
        self,
        query: str | None = None,
        *,
        criteria: object | None = None,
    ) -> HandlerResult:
        self.calls.append(query)
        if self.error is not None:
            raise self.error
        return HandlerResult(
            HandlerOutcome.SUCCESS,
            {"shops": tuple(self.shops)},
        )


class FakeCustomerLookup:
    """Fake application handler that records already-parsed customer input."""

    def __init__(self) -> None:
        self.calls: list[tuple[BookingContext, str, str | None]] = []
        self.result = CustomerVerificationResult(
            phone="0901234567",
            customer_id="customer-1",
            member_rank="gold",
            visit_count=2,
            ng_list_checked=True,
            is_ng_customer=False,
        )

    async def execute(
        self,
        context: BookingContext,
        phone: str,
        name: str | None = None,
    ) -> CustomerVerificationResult:
        self.calls.append((context, phone, name))
        return self.result


class FakePhoneConfirmation:
    """Fake application handler that records confirmation execution."""

    def __init__(self) -> None:
        self.contexts: list[BookingContext] = []

    def execute(self, context: BookingContext) -> None:
        self.contexts.append(context)


class FakeCheckCustomerHandler:
    def __init__(
        self,
        lookup: FakeCustomerLookup | None,
        confirmation: FakePhoneConfirmation | None,
    ) -> None:
        self.lookup = lookup
        self.confirmation = confirmation

    async def check(
        self,
        context: BookingContext,
        phone: str,
        name: str | None = None,
    ) -> HandlerResult:
        assert self.lookup is not None
        verification = await self.lookup.execute(context, phone, name)
        return HandlerResult(
            HandlerOutcome.SUCCESS,
            {"verification": verification},
            {
                "phone": phone,
                "customer": Customer(phone, name),
            },
        )

    def confirm(self, context: BookingContext) -> HandlerResult:
        if self.confirmation is not None:
            self.confirmation.execute(context)
        return HandlerResult(
            HandlerOutcome.SUCCESS,
            context_updates={"phone_confirmed": True},
        )


class FakeCreateBookingHandler(CreateBookingHandler):
    """Fake application handler that records the unchanged idempotency key."""

    def __init__(self) -> None:
        self.calls: list[tuple[BookingContext, str]] = []
        self.result = CreateBookingResult(BOOKING, "RSV-001")

    async def execute(
        self,
        context: BookingContext,
        idempotency_key: str,
    ) -> HandlerResult:
        self.calls.append((context, idempotency_key))
        return HandlerResult(
            HandlerOutcome.SUCCESS,
            {"create_result": self.result},
            {
                "booking": BOOKING,
                "booking_id": BOOKING.booking_id,
                "reservation_code": self.result.reservation_code,
            },
        )


class FakeTherapistAvailabilityGateway:
    def __init__(self, therapists: list[TherapistPreference]) -> None:
        self.therapists = therapists
        self.calls: list[AvailableTherapistRequest] = []

    async def search_available_therapists(
        self,
        request: AvailableTherapistRequest,
    ) -> list[TherapistPreference]:
        self.calls.append(request)
        return self.therapists


class FakeExistingBookingGateway:
    def __init__(self, booking: Booking = BOOKING) -> None:
        self.booking = booking
        self.lookup_calls: list[tuple[str, str]] = []
        self.cancel_calls: list[tuple[UUID, str | None]] = []

    async def lookup_booking(self, booking_reference: str, phone: str) -> Booking:
        self.lookup_calls.append((booking_reference, phone))
        return self.booking

    async def cancel_booking(self, booking_id: UUID, phone: str | None = None) -> Booking:
        self.cancel_calls.append((booking_id, phone))
        return Booking(
            booking_id=booking_id,
            status="cancelled",
            shop=self.booking.shop,
            main_course=self.booking.main_course,
            customer=Customer(phone or self.booking.customer.phone, self.booking.customer.name),
            booking_date=self.booking.booking_date,
            start_time=self.booking.start_time,
            reservation_code=self.booking.reservation_code,
        )


def production_bridge(
    *,
    search_shop: FakeSearchShopHandler | None = None,
    availability: FakeCheckAvailabilityHandler | None = None,
    customer: FakeCustomerLookup | None = None,
    confirmation: FakePhoneConfirmation | None = None,
    create: FakeCreateBookingHandler | None = None,
    booking_gateway: FakeExistingBookingGateway | None = None,
    therapist_availability: FakeTherapistAvailabilityGateway | None = None,
) -> ActionRegistry:
    check_customer = (
        None
        if customer is None and confirmation is None
        else cast(
            CheckCustomerHandler,
            FakeCheckCustomerHandler(customer, confirmation),
        )
    )
    return ActionRegistry(
        search_shop_handler=search_shop,
        check_availability_handler=availability,
        check_customer_handler=check_customer,
        create_booking_handler=create,
        booking_gateway=cast(BookingGateway | None, booking_gateway),
        therapist_availability_gateway=cast(
            TherapistAvailabilityGateway | None,
            therapist_availability,
        ),
    )


@pytest.mark.asyncio
async def test_search_shop_binding_uses_default_query_without_context_mutation() -> None:
    handler = FakeSearchShopHandler()
    bridge = production_bridge(search_shop=handler)
    booking_context = BookingContext(
        conversation_id="conversation-1",
        state=BookingState.IDLE,
        last_failure_code="keep",
    )

    result = await bridge.execute_action(
        "search_shop",
        execution_context(booking_context=booking_context),
    )

    assert handler.calls == [None]
    assert result.output == tuple(handler.shops)
    assert booking_context.state is BookingState.IDLE
    assert booking_context.shop is None
    assert booking_context.last_failure_code is None


@pytest.mark.asyncio
async def test_search_shop_binding_preserves_requested_date_and_time() -> None:
    handler = FakeSearchShopHandler()
    bridge = production_bridge(search_shop=handler)
    booking_context = BookingContext(conversation_id="conversation-1")
    requested_date = date(2099, 8, 5)
    requested_time = time(7, 0)

    await bridge.execute_action(
        "search_shop",
        execution_context(
            booking_context=booking_context,
            payload={
                "booking_date": requested_date,
                "start_time": requested_time,
            },
        ),
    )

    assert booking_context.requested_booking_date == requested_date
    assert booking_context.requested_start_time == requested_time


@pytest.mark.asyncio
async def test_search_shop_failure_preserves_context() -> None:
    handler = FakeSearchShopHandler(error=RuntimeError("POS unavailable"))
    bridge = production_bridge(search_shop=handler)
    booking_context = BookingContext(
        conversation_id="conversation-1",
        state=BookingState.IDLE,
        last_failure_code="keep",
    )

    with pytest.raises(ActionExecutionError):
        await bridge.execute_action(
            "search_shop",
            execution_context(booking_context=booking_context),
        )

    assert handler.calls == [None]
    assert booking_context.state is BookingState.IDLE
    assert booking_context.shop is None
    assert booking_context.last_failure_code == "keep"


@pytest.mark.asyncio
async def test_load_time_slots_binding_stores_slots_only() -> None:
    handler = FakeCheckAvailabilityHandler()
    bridge = production_bridge(availability=handler)
    booking_context = BookingContext(
        conversation_id="conversation-1",
        state=BookingState.SELECTING_SERVICE,
    )

    result = await bridge.execute_action(
        "load_time_slots",
        execution_context(booking_context=booking_context),
    )

    assert handler.contexts == [booking_context]
    assert result.output == handler.slots
    assert booking_context.available_slots == handler.slots
    assert booking_context.start_time is None
    assert booking_context.state is BookingState.SELECTING_SERVICE


@pytest.mark.asyncio
async def test_clear_phone_confirmation_preserves_booking_fields() -> None:
    customer_handler = FakeCustomerLookup()
    bridge = production_bridge(customer=customer_handler)
    booking_context = BookingContext(
        conversation_id="conversation-1",
        state=BookingState.VERIFYING_PHONE,
        shop=SHOP,
        main_course=COURSE,
        booking_date=date(2099, 8, 5),
        start_time=time(10, 30),
        num_customer=1,
        duration_minutes=60,
        phone="0901234567",
        phone_confirmed=True,
        member_rank="gold",
        ng_list_checked=True,
    )

    result = await bridge.execute_action(
        "clear_phone_confirmation",
        execution_context(booking_context=booking_context),
    )

    assert result.output is None
    assert booking_context.phone is None
    assert booking_context.phone_confirmed is False
    assert booking_context.member_rank is None
    assert booking_context.ng_list_checked is False
    assert booking_context.shop is SHOP
    assert booking_context.main_course is COURSE
    assert booking_context.booking_date == date(2099, 8, 5)
    assert booking_context.start_time == time(10, 30)
    assert booking_context.num_customer == 1
    assert booking_context.duration_minutes == 60

    await bridge.execute_action(
        "handle_phone_collection",
        execution_context(
            booking_context=booking_context,
            payload={"phone": "0912345678"},
        ),
    )

    assert customer_handler.calls == [(booking_context, "0912345678", None)]
    assert booking_context.phone == "0912345678"


@pytest.mark.asyncio
async def test_clear_phone_confirmation_rolls_back_with_later_action_failure() -> None:
    bridge = production_bridge()

    async def fail(context: ActionExecutionContext) -> ActionResult:
        raise RuntimeError("later action failed")

    bridge.register_action("fail_after_clear", fail)
    booking_context = BookingContext(
        conversation_id="conversation-1",
        state=BookingState.VERIFYING_PHONE,
        phone="0901234567",
        phone_confirmed=True,
        member_rank="gold",
        ng_list_checked=True,
    )

    with pytest.raises(ActionExecutionError):
        await bridge.execute_actions(
            ("clear_phone_confirmation", "fail_after_clear"),
            execution_context(booking_context=booking_context),
        )

    assert booking_context.phone == "0901234567"
    assert booking_context.phone_confirmed is True
    assert booking_context.member_rank == "gold"
    assert booking_context.ng_list_checked is True


@pytest.mark.asyncio
async def test_reload_time_slots_alias_refreshes_slots_without_changing_time() -> None:
    handler = FakeCheckAvailabilityHandler()
    bridge = production_bridge(availability=handler)
    booking_context = BookingContext(
        conversation_id="conversation-1",
        state=BookingState.BOOKING_FAILED,
        start_time=time(9, 0),
    )

    result = await bridge.execute_action(
        "reload_time_slots",
        execution_context(booking_context=booking_context),
    )

    assert handler.contexts == [booking_context]
    assert result.action_name == "reload_time_slots"
    assert result.output == handler.slots
    assert booking_context.available_slots == handler.slots
    assert booking_context.start_time == time(9, 0)
    assert booking_context.state is BookingState.BOOKING_FAILED


@pytest.mark.asyncio
async def test_reload_time_slots_failure_rolls_back_context() -> None:
    handler = FakeCheckAvailabilityHandler(error=RuntimeError("POS unavailable"))
    bridge = production_bridge(availability=handler)
    stale_slots = (time(9, 0),)
    booking_context = BookingContext(
        conversation_id="conversation-1",
        state=BookingState.BOOKING_FAILED,
        start_time=time(9, 0),
        available_slots=stale_slots,
    )

    with pytest.raises(ActionExecutionError):
        await bridge.execute_action(
            "reload_time_slots",
            execution_context(booking_context=booking_context),
        )

    assert handler.contexts == [booking_context]
    assert booking_context.available_slots == stale_slots
    assert booking_context.start_time == time(9, 0)
    assert booking_context.state is BookingState.BOOKING_FAILED


@pytest.mark.asyncio
async def test_phone_collection_binding_passes_phone_and_optional_name() -> None:
    handler = FakeCustomerLookup()
    bridge = production_bridge(customer=handler)
    booking_context = BookingContext(
        conversation_id="conversation-1",
        state=BookingState.COLLECTING_PHONE,
    )

    await bridge.execute_action(
        "handle_phone_collection",
        execution_context(
            booking_context=booking_context,
            payload={"phone": "0901234567", "name": "Nguyen An"},
        ),
    )

    assert handler.calls == [(booking_context, "0901234567", "Nguyen An")]
    assert booking_context.phone == "0901234567"
    assert booking_context.phone_confirmed is True
    assert booking_context.state is BookingState.COLLECTING_PHONE


@pytest.mark.asyncio
async def test_phone_collection_reuses_existing_customer_name_when_changing_phone() -> None:
    handler = FakeCustomerLookup()
    bridge = production_bridge(customer=handler)
    booking_context = BookingContext(
        conversation_id="conversation-1",
        state=BookingState.COLLECTING_PHONE,
        phone="07733582649",
        customer=Customer("07733582649", "Lam"),
        phone_confirmed=True,
    )

    await bridge.execute_action(
        "handle_phone_collection",
        execution_context(
            booking_context=booking_context,
            payload={"phone": "0773582641"},
        ),
    )

    assert handler.calls == [(booking_context, "0773582641", "Lam")]
    assert booking_context.phone == "0773582641"
    assert booking_context.customer == Customer("0773582641", "Lam")
    assert booking_context.phone_confirmed is True


@pytest.mark.asyncio
async def test_phone_collection_rejects_missing_or_untyped_phone() -> None:
    bridge = production_bridge(customer=FakeCustomerLookup())

    for payload in ({}, {"phone": 901234567}):
        with pytest.raises(ActionExecutionError) as exc_info:
            await bridge.execute_action(
                "handle_phone_collection",
                execution_context(payload=payload),
            )
        assert isinstance(exc_info.value.__cause__, InvalidActionInputError)


@pytest.mark.asyncio
async def test_phone_confirmation_binding_does_not_change_state() -> None:
    handler = FakePhoneConfirmation()
    bridge = production_bridge(confirmation=handler)
    booking_context = BookingContext(
        conversation_id="conversation-1",
        state=BookingState.VERIFYING_PHONE,
        phone="0901234567",
    )

    await bridge.execute_action(
        "mark_phone_confirmed",
        execution_context(booking_context=booking_context),
    )

    assert handler.contexts == [booking_context]
    assert booking_context.phone_confirmed is True
    assert booking_context.state is BookingState.VERIFYING_PHONE


@pytest.mark.asyncio
async def test_customer_name_collection_marks_phone_confirmed_for_new_customer() -> None:
    bridge = production_bridge(customer=FakeCustomerLookup())
    booking_context = BookingContext(
        conversation_id="conversation-1",
        state=BookingState.COLLECTING_NAME,
        phone="0901234567",
    )

    await bridge.execute_action(
        "handle_customer_name",
        execution_context(
            booking_context=booking_context,
            payload={"name": "Nguyen An"},
        ),
    )

    assert booking_context.customer == Customer("0901234567", "Nguyen An")
    assert booking_context.phone_confirmed is True


@pytest.mark.asyncio
async def test_create_binding_preserves_idempotency_and_does_not_commit_state() -> None:
    handler = FakeCreateBookingHandler()
    bridge = production_bridge(create=handler)
    booking_context = BookingContext(
        conversation_id="conversation-1",
        state=BookingState.BOOKING_EXECUTING,
    )

    await bridge.execute_action(
        "create_booking",
        execution_context(
            booking_context=booking_context,
            idempotency_key="conversation-1:stable-attempt",
        ),
    )

    assert handler.calls == [
        (booking_context, "conversation-1:stable-attempt"),
    ]
    assert booking_context.booking is BOOKING
    assert booking_context.state is BookingState.BOOKING_EXECUTING


@pytest.mark.asyncio
async def test_lookup_existing_booking_for_cancel_does_not_cancel_before_confirmation() -> None:
    gateway = FakeExistingBookingGateway()
    bridge = production_bridge(booking_gateway=gateway)
    booking_context = BookingContext(conversation_id="conversation-1")

    report = await bridge.execute_actions(
        ("lookup_existing_booking_for_cancel",),
        execution_context(
            booking_context=booking_context,
            payload={
                "booking_reference": str(BOOKING.booking_id),
                "phone": "0901234567",
            },
        ),
    )

    assert report.executed_action_names == ("lookup_existing_booking_for_cancel",)
    assert gateway.lookup_calls == [(str(BOOKING.booking_id), "0901234567")]
    assert gateway.cancel_calls == []
    assert booking_context.booking is not None
    assert booking_context.booking.status == "confirmed"
    assert booking_context.booking_id == BOOKING.booking_id
    assert booking_context.phone == "0901234567"


@pytest.mark.asyncio
async def test_cancel_existing_booking_uses_preloaded_booking_after_confirmation() -> None:
    gateway = FakeExistingBookingGateway()
    bridge = production_bridge(booking_gateway=gateway)
    booking_context = BookingContext(
        conversation_id="conversation-1",
        booking=BOOKING,
        booking_id=BOOKING.booking_id,
        phone="0901234567",
    )

    report = await bridge.execute_actions(
        ("cancel_existing_booking",),
        execution_context(booking_context=booking_context),
    )

    assert report.executed_action_names == ("cancel_existing_booking",)
    assert gateway.lookup_calls == []
    assert gateway.cancel_calls == [(BOOKING.booking_id, "0901234567")]
    assert booking_context.booking is not None
    assert booking_context.booking.status == "cancelled"
    assert booking_context.booking_id == BOOKING.booking_id
    assert booking_context.phone == "0901234567"


@pytest.mark.asyncio
async def test_lookup_cancel_missing_identity_preserves_partial_context() -> None:
    gateway = FakeExistingBookingGateway()
    bridge = production_bridge(booking_gateway=gateway)
    booking_context = BookingContext(conversation_id="conversation-1")

    with pytest.raises(ActionExecutionError) as error_info:
        await bridge.execute_actions(
            ("lookup_existing_booking_for_cancel",),
            execution_context(
                booking_context=booking_context,
                payload={"phone": "0901234567"},
            ),
        )

    assert bridge.get_failure_code(error_info.value) == "cancel_booking_identity_missing"
    assert booking_context.phone == "0901234567"
    assert booking_context.cancel_booking_reference is None
    assert gateway.lookup_calls == []
    assert gateway.cancel_calls == []


@pytest.mark.asyncio
async def test_change_time_keeps_personal_therapist_when_still_available() -> None:
    therapist = TherapistPreference(
        TherapistPreferenceType.PERSONAL,
        therapist_id="therapist-1",
        therapist_name="Nguyen An",
    )
    gateway = FakeTherapistAvailabilityGateway([therapist])
    bridge = production_bridge(therapist_availability=gateway)
    booking_context = BookingContext(
        conversation_id="conversation-1",
        state=BookingState.AWAITING_CONFIRMATION,
        shop=SHOP,
        main_course=COURSE,
        booking_date=date(2099, 8, 1),
        start_time=time(10, 30),
        num_customer=1,
        duration_minutes=60,
        therapist_preference=therapist,
        therapist_verified=True,
        available_slots=(time(13, 0), time(13, 30)),
    )

    await bridge.execute_action(
        "change_time",
        execution_context(
            booking_context=booking_context,
            payload={"start_time": time(13, 0)},
        ),
    )

    assert booking_context.start_time == time(13, 0)
    assert booking_context.therapist_preference == therapist
    assert booking_context.therapist_verified is True
    assert booking_context.last_failure_code is None
    assert gateway.calls[0].start_time == time(13, 0)
    assert gateway.calls[0].end_time == time(14, 0)


@pytest.mark.asyncio
async def test_change_customer_name_preserves_phone_verification() -> None:
    bridge = production_bridge()
    booking_context = BookingContext(
        conversation_id="conversation-1",
        state=BookingState.AWAITING_CONFIRMATION,
        phone="0901234567",
        phone_confirmed=True,
        customer=Customer(phone="0901234567", name="Nguyen An"),
    )

    await bridge.execute_action(
        "change_customer_name",
        execution_context(
            booking_context=booking_context,
            payload={"name": "Le Minh"},
        ),
    )

    assert booking_context.phone == "0901234567"
    assert booking_context.phone_confirmed is True
    assert booking_context.customer == Customer(phone="0901234567", name="Le Minh")


@pytest.mark.asyncio
async def test_change_addon_preserves_main_course_and_clears_availability() -> None:
    bridge = production_bridge()
    booking_context = BookingContext(
        conversation_id="conversation-1",
        state=BookingState.AWAITING_CONFIRMATION,
        main_course=COURSE,
        start_time=time(10, 30),
        available_slots=(time(10, 30),),
        therapist_preference=TherapistPreference(TherapistPreferenceType.FEMALE),
        therapist_verified=True,
    )

    await bridge.execute_action(
        "change_addon",
        execution_context(booking_context=booking_context),
    )

    assert booking_context.main_course == COURSE
    assert booking_context.addons == ()
    assert booking_context.available_slots is None
    assert booking_context.start_time is None
    assert booking_context.therapist_preference is None
    assert booking_context.therapist_verified is False


@pytest.mark.asyncio
async def test_change_time_clears_personal_therapist_when_unavailable() -> None:
    therapist = TherapistPreference(
        TherapistPreferenceType.PERSONAL,
        therapist_id="therapist-1",
        therapist_name="Nguyen An",
    )
    other_therapist = TherapistPreference(
        TherapistPreferenceType.PERSONAL,
        therapist_id="therapist-2",
        therapist_name="Le Binh",
    )
    bridge = production_bridge(
        therapist_availability=FakeTherapistAvailabilityGateway([other_therapist])
    )
    booking_context = BookingContext(
        conversation_id="conversation-1",
        state=BookingState.AWAITING_CONFIRMATION,
        shop=SHOP,
        main_course=COURSE,
        booking_date=date(2099, 8, 1),
        start_time=time(10, 30),
        num_customer=1,
        duration_minutes=60,
        therapist_preference=therapist,
        therapist_verified=True,
        available_slots=(time(13, 0),),
    )

    await bridge.execute_action(
        "change_time",
        execution_context(
            booking_context=booking_context,
            payload={"start_time": time(13, 0)},
        ),
    )

    assert booking_context.start_time == time(13, 0)
    assert booking_context.therapist_preference is None
    assert booking_context.therapist_verified is False
    assert booking_context.last_failure_code == "therapist_unavailable"


@pytest.mark.asyncio
async def test_change_time_keeps_group_booking_without_therapist_question() -> None:
    bridge = production_bridge()
    booking_context = BookingContext(
        conversation_id="conversation-1",
        state=BookingState.AWAITING_CONFIRMATION,
        shop=SHOP,
        main_course=COURSE,
        booking_date=date(2099, 8, 1),
        start_time=time(10, 30),
        num_customer=2,
        duration_minutes=60,
        therapist_verified=True,
        available_slots=(time(13, 0),),
    )

    await bridge.execute_action(
        "change_time",
        execution_context(
            booking_context=booking_context,
            payload={"start_time": time(13, 0)},
        ),
    )

    assert booking_context.start_time == time(13, 0)
    assert booking_context.therapist_preference == TherapistPreference(
        TherapistPreferenceType.NONE
    )
    assert booking_context.therapist_verified is True


@pytest.mark.parametrize("num_customer", [2, 3])
@pytest.mark.asyncio
async def test_group_therapist_skip_uses_domain_api(num_customer: int) -> None:
    booking_context = BookingContext(
        conversation_id="conversation-1",
        state=BookingState.SELECTING_THERAPIST,
        num_customer=num_customer,
    )

    await ActionRegistry().execute_action(
        "skip_therapist_for_group",
        execution_context(booking_context=booking_context),
    )

    assert booking_context.therapist_preference == TherapistPreference(TherapistPreferenceType.NONE)
    assert booking_context.state is BookingState.SELECTING_THERAPIST


@pytest.mark.asyncio
async def test_single_customer_cannot_use_group_therapist_skip() -> None:
    booking_context = BookingContext(
        conversation_id="conversation-1",
        num_customer=1,
    )

    with pytest.raises(ActionExecutionError) as exc_info:
        await ActionRegistry().execute_action(
            "skip_therapist_for_group",
            execution_context(booking_context=booking_context),
        )

    assert isinstance(exc_info.value.__cause__, InvalidActionInputError)


def test_find_unregistered_actions_deduplicates_in_declaration_order() -> None:
    bridge = ActionRegistry()

    assert bridge.find_unregistered_actions(
        (
            "missing_first",
            "handle_people_selection",
            "missing_second",
            "missing_first",
        )
    ) == ("missing_first", "missing_second")


def test_injected_handlers_register_only_available_bindings() -> None:
    bridge = production_bridge(
        search_shop=FakeSearchShopHandler(),
        availability=FakeCheckAvailabilityHandler(),
        customer=FakeCustomerLookup(),
        confirmation=FakePhoneConfirmation(),
        create=FakeCreateBookingHandler(),
    )

    assert (
        bridge.find_unregistered_actions(
            (
                "load_time_slots",
                "reload_time_slots",
                "search_shop",
                "clear_phone_confirmation",
                "handle_phone_collection",
                "mark_phone_confirmed",
                "create_booking",
            )
        )
        == ()
    )


def wrapped_error(
    action_name: str,
    cause: Exception,
) -> ActionExecutionError:
    return ActionExecutionError(action_name, (), cause)


@pytest.mark.parametrize(
    ("action_name", "cause", "expected"),
    [
        ("create_booking", SlotConflictError(), "booking_conflict"),
        ("load_time_slots", SlotConflictError(), "no_slots_available"),
        ("handle_time_selection", SlotConflictError(), "slot_unavailable"),
        (
            "handle_phone_collection",
            InvalidBookingDataError("sensitive message"),
            "invalid_phone",
        ),
        (
            "load_time_slots",
            BookingContextNotReadyError(),
            "booking_data_incomplete",
        ),
        (
            "handle_phone_collection",
            CustomerNotAllowedError(),
            "customer_ng_blocked",
        ),
        (
            "handle_phone_collection",
            CustomerVerificationMismatchError(),
            "customer_verification_mismatch",
        ),
        ("custom_action", UnknownActionError(), "unknown_action_error"),
        (
            "custom_action",
            InvalidActionInputError(),
            "booking_data_incomplete",
        ),
        (
            "custom_action",
            InvalidActionSequenceError(),
            "action_sequence_invalid",
        ),
        (
            "custom_action",
            InvalidFlowConditionError(),
            "flow_configuration_error",
        ),
        ("custom_action", RuntimeError("invalid phone"), "action_execution_error"),
        ("load_time_slots", RuntimeError("gateway failed"), "slot_api_error"),
        ("create_booking", RuntimeError("gateway failed"), "booking_api_error"),
        (
            "handle_phone_collection",
            RuntimeError("gateway failed"),
            "booking_api_error",
        ),
    ],
)
def test_failure_code_mapping_is_type_based_and_action_aware(
    action_name: str,
    cause: Exception,
    expected: str,
) -> None:
    bridge = ActionRegistry()

    assert bridge.get_failure_code(wrapped_error(action_name, cause)) == expected


def test_failure_mapping_unwraps_only_explicit_action_wrappers() -> None:
    root = SlotConflictError()
    nested = wrapped_error("inner", root)
    outer = wrapped_error("create_booking", nested)

    descriptor = ActionRegistry().describe_failure(outer)

    assert descriptor == FailureDescriptor(
        code="booking_conflict",
        action_name="create_booking",
        cause=root,
    )
    assert descriptor.cause is root


def test_custom_failure_code_provider_receives_root_exception() -> None:
    received: list[Exception] = []

    def provider(error: Exception) -> str:
        received.append(error)
        return "custom_failure"

    cause = RuntimeError("private details")
    bridge = ActionRegistry(failure_code_provider=provider)

    assert bridge.get_failure_code(wrapped_error("custom_action", cause)) == "custom_failure"
    assert received == [cause]


@pytest.mark.asyncio
async def test_failure_actions_execute_in_order_without_applying_target() -> None:
    calls: list[str] = []
    bridge = ActionRegistry()
    booking_context = BookingContext(
        conversation_id="conversation-1",
        state=BookingState.SELECTING_SERVICE,
        booking_date=date(2099, 8, 1),
    )

    async def suggest(context: ActionExecutionContext) -> ActionResult:
        assert context.booking_context.booking_date is None
        calls.append("suggest_nearest_time")
        return ActionResult("suggest_nearest_time")

    async def prepare(context: ActionExecutionContext) -> ActionResult:
        context.booking_context.set_booking_date(None)
        return ActionResult("prepare_recovery")

    bridge.register_action("prepare_recovery", prepare)
    bridge.register_action("suggest_nearest_time", suggest)
    failure = FlowFailure(
        "no_slots_available",
        BookingState.SELECTING_DATE,
        ("prepare_recovery", "suggest_nearest_time"),
        "no_slots_available",
    )

    report = await bridge.execute_failure_actions(
        failure,
        execution_context(booking_context=booking_context),
    )

    assert report.executed_action_names == (
        "prepare_recovery",
        "suggest_nearest_time",
    )
    assert calls == ["suggest_nearest_time"]
    assert booking_context.booking_date is None
    assert booking_context.state is BookingState.SELECTING_SERVICE


@pytest.mark.asyncio
async def test_failed_failure_action_stops_and_rolls_back_local_context() -> None:
    calls: list[str] = []
    bridge = ActionRegistry()
    booking_context = BookingContext(
        conversation_id="conversation-1",
        state=BookingState.SELECTING_TIME,
        phone="original",
    )

    async def first(context: ActionExecutionContext) -> ActionResult:
        calls.append("first_recovery")
        context.booking_context.phone = "mutated"
        return ActionResult("first_recovery")

    async def second(context: ActionExecutionContext) -> ActionResult:
        calls.append("second_recovery")
        raise RuntimeError("recovery failed")

    async def third(context: ActionExecutionContext) -> ActionResult:
        calls.append("third_recovery")
        return ActionResult("third_recovery")

    bridge.register_action("first_recovery", first)
    bridge.register_action("second_recovery", second)
    bridge.register_action("third_recovery", third)
    failure = FlowFailure(
        "slot_unavailable",
        BookingState.SELECTING_TIME,
        ("first_recovery", "second_recovery", "third_recovery"),
    )

    with pytest.raises(ActionExecutionError) as exc_info:
        await bridge.execute_failure_actions(
            failure,
            execution_context(booking_context=booking_context),
        )

    assert calls == ["first_recovery", "second_recovery"]
    assert exc_info.value.executed_actions == ("first_recovery",)
    assert booking_context.phone == "original"
    assert booking_context.state is BookingState.SELECTING_TIME


@pytest.mark.asyncio
async def test_empty_failure_actions_return_empty_report() -> None:
    report = await ActionRegistry().execute_failure_actions(
        FlowFailure("failure", BookingState.SELECTING_TIME),
        execution_context(),
    )

    assert report.results == ()


@pytest.mark.asyncio
async def test_failure_actions_reject_booking_side_effect_before_execution() -> None:
    calls: list[str] = []
    bridge = ActionRegistry()

    async def first(context: ActionExecutionContext) -> ActionResult:
        calls.append("first_recovery")
        return ActionResult("first_recovery")

    bridge.register_action("first_recovery", first)
    failure = FlowFailure(
        "failure",
        BookingState.BOOKING_FAILED,
        ("first_recovery", "create_booking"),
    )

    with pytest.raises(InvalidActionSequenceError):
        await bridge.execute_failure_actions(
            failure,
            execution_context(idempotency_key="stable-key"),
        )

    assert calls == []
