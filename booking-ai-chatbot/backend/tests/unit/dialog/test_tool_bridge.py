"""Tests for the explicit dialog action registry and executor."""

from collections.abc import Mapping
from datetime import date, time
from decimal import Decimal
from typing import cast
from uuid import UUID

import pytest

from app.application.exceptions import (
    CustomerVerificationMismatchError,
    SlotConflictError,
)
from app.application.handlers.check_availability_handler import (
    CheckAvailabilityHandler,
)
from app.application.handlers.collect_customer_handler import CollectCustomerHandler
from app.application.handlers.confirm_phone_handler import ConfirmPhoneHandler
from app.application.handlers.create_booking_handler import CreateBookingHandler
from app.application.handlers.search_shop_handler import SearchShopHandler
from app.application.ports.booking_gateway import (
    CreateBookingResult,
    CustomerVerificationResult,
)
from app.dialog.flow_loader import FlowFailure, InvalidFlowConditionError
from app.dialog.tool_bridge import (
    ActionCallable,
    ActionExecutionContext,
    ActionExecutionError,
    ActionResult,
    DuplicateActionError,
    FailureDescriptor,
    InvalidActionInputError,
    InvalidActionNameError,
    InvalidActionSequenceError,
    ToolBridge,
    UnknownActionError,
)
from app.domain.booking import Booking, Customer, Service, Shop
from app.domain.booking_context import BookingContext
from app.domain.booking_state import BookingState
from app.domain.exceptions import (
    BookingContextNotReadyError,
    CustomerNotAllowedError,
    InvalidBookingDataError,
)

SHOP = Shop(
    UUID("11111111-1111-1111-1111-111111111111"),
    "Central Spa",
)
SERVICE = Service(
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
    service=SERVICE,
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
        booking_context=booking_context
        or BookingContext(conversation_id="conversation-1"),
        intent="test_intent",
        payload=payload or {},
        idempotency_key=idempotency_key,
    )


async def successful_action(context: ActionExecutionContext) -> ActionResult:
    """Return a deterministic result for registry tests."""
    return ActionResult("custom_action", context.intent)


def test_register_lookup_order_and_instance_isolation() -> None:
    first = ToolBridge()
    second = ToolBridge()
    initial_names = first.registered_actions()

    first.register_action("custom_action", successful_action)

    assert first.has_action("custom_action") is True
    assert first.get_action("custom_action") is successful_action
    assert first.registered_actions() == initial_names + ("custom_action",)
    assert second.has_action("custom_action") is False


def test_duplicate_action_is_rejected_without_override() -> None:
    bridge = ToolBridge()
    bridge.register_action("custom_action", successful_action)

    with pytest.raises(DuplicateActionError):
        bridge.register_action("custom_action", successful_action)

    assert bridge.get_action("custom_action") is successful_action


def test_unknown_action_is_rejected() -> None:
    with pytest.raises(UnknownActionError):
        ToolBridge().get_action("missing_action")


@pytest.mark.asyncio
async def test_unknown_executed_action_is_wrapped_for_failure_mapping() -> None:
    bridge = ToolBridge()

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
        ToolBridge().register_action(name, successful_action)


def test_non_callable_action_is_rejected() -> None:
    with pytest.raises(TypeError):
        ToolBridge().register_action(
            "not_callable",
            cast(ActionCallable, object()),
        )


@pytest.mark.asyncio
async def test_custom_async_action_can_be_executed() -> None:
    bridge = ToolBridge()
    bridge.register_action("custom_action", successful_action)

    result = await bridge.execute_action("custom_action", execution_context())

    assert result == ActionResult("custom_action", "test_intent")


@pytest.mark.asyncio
async def test_actions_execute_sequentially_in_declared_order() -> None:
    calls: list[str] = []
    bridge = ToolBridge()

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
    report = await ToolBridge().execute_actions((), execution_context())

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
    bridge = ToolBridge()

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
    bridge = ToolBridge()

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
    bridge = ToolBridge()

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
        ("retry_booking", "after"),
        ("create_booking", "retry_booking"),
        ("create_booking", "create_booking"),
    ],
)
@pytest.mark.asyncio
async def test_unsafe_side_effect_sequence_is_rejected_before_execution(
    action_names: tuple[str, ...],
) -> None:
    calls: list[str] = []
    bridge = ToolBridge()

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
    bridge = ToolBridge()

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
    bridge = ToolBridge()

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
    bridge = ToolBridge()

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

    def __init__(self) -> None:
        self.contexts: list[BookingContext] = []
        self.slots = (time(10, 30), time(11, 0))

    async def execute(self, context: BookingContext) -> tuple[time, ...]:
        self.contexts.append(context)
        context.set_available_slots(self.slots)
        return self.slots


class FakeSearchShopHandler(SearchShopHandler):
    """Fake application handler that records default shop searches."""

    def __init__(self, *, error: Exception | None = None) -> None:
        self.calls: list[str | None] = []
        self.shops = [SHOP]
        self.error = error

    async def execute(self, query: str | None = None) -> list[Shop]:
        self.calls.append(query)
        if self.error is not None:
            raise self.error
        return self.shops


class FakeCollectCustomerHandler(CollectCustomerHandler):
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
        context.set_phone(phone)
        context.customer = Customer(phone, name)
        return self.result


class FakeConfirmPhoneHandler(ConfirmPhoneHandler):
    """Fake application handler that records confirmation execution."""

    def __init__(self) -> None:
        self.contexts: list[BookingContext] = []

    def execute(self, context: BookingContext) -> None:
        self.contexts.append(context)
        context.confirm_phone()


class FakeCreateBookingHandler(CreateBookingHandler):
    """Fake application handler that records the unchanged idempotency key."""

    def __init__(self) -> None:
        self.calls: list[tuple[BookingContext, str]] = []
        self.result = CreateBookingResult(BOOKING, "RSV-001")

    async def execute(
        self,
        context: BookingContext,
        idempotency_key: str,
    ) -> CreateBookingResult:
        self.calls.append((context, idempotency_key))
        context.booking = BOOKING
        context.booking_id = BOOKING.booking_id
        return self.result


def production_bridge(
    *,
    search_shop: FakeSearchShopHandler | None = None,
    availability: FakeCheckAvailabilityHandler | None = None,
    customer: FakeCollectCustomerHandler | None = None,
    confirmation: FakeConfirmPhoneHandler | None = None,
    create: FakeCreateBookingHandler | None = None,
) -> ToolBridge:
    return ToolBridge(
        search_shop_handler=search_shop,
        check_availability_handler=availability,
        collect_customer_handler=customer,
        confirm_phone_handler=confirmation,
        create_booking_handler=create,
    )


@pytest.mark.asyncio
async def test_search_shop_binding_uses_default_query_without_context_mutation() -> None:
    handler = FakeSearchShopHandler()
    bridge = production_bridge(search_shop=handler)
    booking_context = BookingContext(
        conversation_id="conversation-1",
        state=BookingState.IDLE,
        pending_action="keep",
    )

    result = await bridge.execute_action(
        "search_shop",
        execution_context(booking_context=booking_context),
    )

    assert handler.calls == [None]
    assert result.output is handler.shops
    assert booking_context.state is BookingState.IDLE
    assert booking_context.shop is None
    assert booking_context.pending_action == "keep"


@pytest.mark.asyncio
async def test_search_shop_failure_preserves_context() -> None:
    handler = FakeSearchShopHandler(error=RuntimeError("POS unavailable"))
    bridge = production_bridge(search_shop=handler)
    booking_context = BookingContext(
        conversation_id="conversation-1",
        state=BookingState.IDLE,
        pending_action="keep",
    )

    with pytest.raises(ActionExecutionError):
        await bridge.execute_action(
            "search_shop",
            execution_context(booking_context=booking_context),
        )

    assert handler.calls == [None]
    assert booking_context.state is BookingState.IDLE
    assert booking_context.shop is None
    assert booking_context.pending_action == "keep"


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
async def test_phone_collection_binding_passes_phone_and_optional_name() -> None:
    handler = FakeCollectCustomerHandler()
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
    assert booking_context.phone_confirmed is False
    assert booking_context.state is BookingState.COLLECTING_PHONE


@pytest.mark.asyncio
async def test_phone_collection_rejects_missing_or_untyped_phone() -> None:
    bridge = production_bridge(customer=FakeCollectCustomerHandler())

    for payload in ({}, {"phone": 901234567}):
        with pytest.raises(ActionExecutionError) as exc_info:
            await bridge.execute_action(
                "handle_phone_collection",
                execution_context(payload=payload),
            )
        assert isinstance(exc_info.value.__cause__, InvalidActionInputError)


@pytest.mark.asyncio
async def test_phone_confirmation_binding_does_not_change_state() -> None:
    handler = FakeConfirmPhoneHandler()
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


@pytest.mark.parametrize("action_name", ["create_booking", "retry_booking"])
@pytest.mark.asyncio
async def test_create_bindings_preserve_idempotency_and_do_not_commit_state(
    action_name: str,
) -> None:
    handler = FakeCreateBookingHandler()
    bridge = production_bridge(create=handler)
    booking_context = BookingContext(
        conversation_id="conversation-1",
        state=BookingState.BOOKING_EXECUTING,
    )

    await bridge.execute_action(
        action_name,
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


@pytest.mark.parametrize("num_customer", [2, 3])
@pytest.mark.asyncio
async def test_group_therapist_skip_uses_domain_api(num_customer: int) -> None:
    booking_context = BookingContext(
        conversation_id="conversation-1",
        state=BookingState.SELECTING_THERAPIST,
        num_customer=num_customer,
    )

    await ToolBridge().execute_action(
        "skip_therapist_for_group",
        execution_context(booking_context=booking_context),
    )

    assert booking_context.therapist_preference is None
    assert booking_context.state is BookingState.SELECTING_THERAPIST


@pytest.mark.asyncio
async def test_single_customer_cannot_use_group_therapist_skip() -> None:
    booking_context = BookingContext(
        conversation_id="conversation-1",
        num_customer=1,
    )

    with pytest.raises(ActionExecutionError) as exc_info:
        await ToolBridge().execute_action(
            "skip_therapist_for_group",
            execution_context(booking_context=booking_context),
        )

    assert isinstance(exc_info.value.__cause__, InvalidActionInputError)


def test_find_unregistered_actions_deduplicates_in_declaration_order() -> None:
    bridge = ToolBridge()

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
        customer=FakeCollectCustomerHandler(),
        confirmation=FakeConfirmPhoneHandler(),
        create=FakeCreateBookingHandler(),
    )

    assert bridge.find_unregistered_actions(
        (
            "load_time_slots",
            "search_shop",
            "handle_phone_collection",
            "mark_phone_confirmed",
            "create_booking",
            "retry_booking",
        )
    ) == ()


def wrapped_error(
    action_name: str,
    cause: Exception,
) -> ActionExecutionError:
    return ActionExecutionError(action_name, (), cause)


@pytest.mark.parametrize(
    ("action_name", "cause", "expected"),
    [
        ("create_booking", SlotConflictError(), "booking_conflict"),
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
    bridge = ToolBridge()

    assert bridge.get_failure_code(wrapped_error(action_name, cause)) == expected


def test_failure_mapping_unwraps_only_explicit_action_wrappers() -> None:
    root = SlotConflictError()
    nested = wrapped_error("inner", root)
    outer = wrapped_error("create_booking", nested)

    descriptor = ToolBridge().describe_failure(outer)

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
    bridge = ToolBridge(failure_code_provider=provider)

    assert (
        bridge.get_failure_code(wrapped_error("custom_action", cause))
        == "custom_failure"
    )
    assert received == [cause]


@pytest.mark.asyncio
async def test_failure_actions_execute_in_order_without_applying_target() -> None:
    calls: list[str] = []
    bridge = ToolBridge()
    booking_context = BookingContext(
        conversation_id="conversation-1",
        state=BookingState.SELECTING_SERVICE,
        booking_date=date(2099, 8, 1),
    )

    async def suggest(context: ActionExecutionContext) -> ActionResult:
        assert context.booking_context.booking_date is None
        calls.append("suggest_nearest_time")
        return ActionResult("suggest_nearest_time")

    bridge.register_action("suggest_nearest_time", suggest)
    failure = FlowFailure(
        "no_slots_available",
        BookingState.SELECTING_DATE,
        ("clear_date", "suggest_nearest_time"),
        "no_slots_available",
    )

    report = await bridge.execute_failure_actions(
        failure,
        execution_context(booking_context=booking_context),
    )

    assert report.executed_action_names == (
        "clear_date",
        "suggest_nearest_time",
    )
    assert calls == ["suggest_nearest_time"]
    assert booking_context.booking_date is None
    assert booking_context.state is BookingState.SELECTING_SERVICE


@pytest.mark.asyncio
async def test_failed_failure_action_stops_and_rolls_back_local_context() -> None:
    calls: list[str] = []
    bridge = ToolBridge()
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
    report = await ToolBridge().execute_failure_actions(
        FlowFailure("failure", BookingState.SELECTING_TIME),
        execution_context(),
    )

    assert report.results == ()


@pytest.mark.parametrize("side_effect", ["create_booking", "retry_booking"])
@pytest.mark.asyncio
async def test_failure_actions_reject_booking_side_effect_before_execution(
    side_effect: str,
) -> None:
    calls: list[str] = []
    bridge = ToolBridge()

    async def first(context: ActionExecutionContext) -> ActionResult:
        calls.append("first_recovery")
        return ActionResult("first_recovery")

    bridge.register_action("first_recovery", first)
    failure = FlowFailure(
        "failure",
        BookingState.BOOKING_FAILED,
        ("first_recovery", side_effect),
    )

    with pytest.raises(InvalidActionSequenceError):
        await bridge.execute_failure_actions(
            failure,
            execution_context(idempotency_key="stable-key"),
        )

    assert calls == []
