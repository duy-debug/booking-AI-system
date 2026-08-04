"""Integration tests for the complete in-process application object graph."""

from datetime import date, time
from decimal import Decimal
from uuid import UUID

import httpx
import pytest

import app.dependencies as dependencies
from app.application.handlers.check_availability_handler import CheckAvailabilityHandler
from app.application.handlers.confirm_phone_handler import ConfirmPhoneHandler
from app.application.ports.booking_gateway import (
    AvailabilityRequest,
    BookingGateway,
    ChildReservationReference,
    CourseSearchRequest,
    CreateBookingRequest,
    CreateBookingResult,
    CustomerVerificationRequest,
    CustomerVerificationResult,
    FinalAvailabilityRequest,
    FinalAvailabilityResult,
)
from app.core.config import Settings
from app.dependencies import ApplicationContainer, create_application_container
from app.dialog.dialog_controller import DialogTurnInput, DialogTurnStatus
from app.dialog.instruction_builder import DialogResponseDraft
from app.dialog.tool_bridge import ActionExecutionContext, ActionResult
from app.domain.booking import (
    Booking,
    CourseSelection,
    Customer,
    Service,
    Shop,
    TherapistPreference,
    TherapistPreferenceType,
)
from app.domain.booking_context import BookingContext
from app.domain.booking_state import BookingState
from app.infrastructure.booking_api.http_booking_gateway import HTTPBookingGateway
from app.infrastructure.cache.memory_cache import MemoryCache
from app.infrastructure.llm.gemini_llm_gateway import GeminiLLMGateway

REQUIRED_ACTIONS = {
    "search_shop",
    "handle_store_selection",
    "handle_date_selection",
    "handle_people_selection",
    "handle_duration_selection",
    "handle_service_selection",
    "load_time_slots",
    "handle_time_selection",
    "handle_therapist_selection",
    "skip_therapist",
    "skip_therapist_for_group",
    "handle_phone_collection",
    "validate_phone",
    "mark_phone_confirmed",
    "create_booking",
    "retry_booking",
}

SHOP = Shop(
    shop_id=UUID("11111111-1111-1111-1111-111111111111"),
    name="Shibuya",
    address="Tokyo",
)
SERVICE = Service(
    service_id=UUID("22222222-2222-2222-2222-222222222222"),
    name="Aromatherapy",
    duration_minutes=60,
    price=Decimal("500000.00"),
)


class FailingAvailabilityHandler(CheckAvailabilityHandler):
    def __init__(self) -> None:
        self.calls = 0

    async def execute(self, context: BookingContext) -> tuple[time, ...]:
        self.calls += 1
        context.set_available_slots((time(11, 0),))
        raise RuntimeError("POS unavailable")


class RecordingBookingGateway:
    def __init__(self, *, create_error: Exception | None = None) -> None:
        self.create_error = create_error
        self.available_slots: tuple[time, ...] = (time(10, 30), time(11, 0))
        self.final_requests: list[FinalAvailabilityRequest] = []
        self.create_requests: list[CreateBookingRequest] = []

    async def search_shops(self, query: str | None = None) -> list[Shop]:
        return [SHOP]

    async def search_services(self, request: CourseSearchRequest) -> list[Service]:
        return [SERVICE]

    async def get_available_slots(
        self,
        request: AvailabilityRequest,
    ) -> tuple[time, ...]:
        return self.available_slots

    async def verify_customer(
        self,
        request: CustomerVerificationRequest,
    ) -> CustomerVerificationResult:
        return CustomerVerificationResult(
            phone=request.phone,
            customer_id="customer-1",
            member_rank="gold",
            visit_count=2,
            ng_list_checked=True,
            is_ng_customer=False,
        )

    async def check_final_availability(
        self,
        request: FinalAvailabilityRequest,
    ) -> FinalAvailabilityResult:
        self.final_requests.append(request)
        return FinalAvailabilityResult(available=True)

    async def create_booking(
        self,
        request: CreateBookingRequest,
    ) -> CreateBookingResult:
        self.create_requests.append(request)
        if self.create_error is not None:
            raise self.create_error
        booking = Booking(
            booking_id=UUID("33333333-3333-3333-3333-333333333333"),
            status="confirmed",
            shop=SHOP,
            service=SERVICE,
            customer=Customer(request.phone, request.customer_name),
            booking_date=request.booking_date,
            start_time=request.start_time,
            num_customer=request.num_customer,
            duration_minutes=request.duration_minutes,
            therapist_preference=request.therapist_preference,
        )
        children = tuple(
            ChildReservationReference(
                UUID(f"44444444-4444-4444-4444-{index:012d}"),
                participant_index=index,
            )
            for index in range(1, request.num_customer + 1)
        )
        return CreateBookingResult(booking, child_reservations=children)

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


async def advance_to_awaiting_confirmation(
    container: ApplicationContainer,
    *,
    num_customer: int,
    therapist_preference: TherapistPreference | None,
) -> tuple[BookingContext, tuple[BookingState, ...]]:
    context = BookingContext(conversation_id=f"e2e-{num_customer}")
    states: list[BookingState] = []

    async def turn(intent: str, payload: dict[str, object]) -> None:
        result = await container.dialog_controller.handle_turn(
            context,
            DialogTurnInput(intent=intent, payload=payload),
        )
        assert result.status is DialogTurnStatus.SUCCESS
        states.append(context.state)

    await turn("start_booking", {})
    await turn("select_store", {"shop": SHOP})
    await turn("select_date", {"booking_date": date(2099, 8, 5)})
    await turn("select_people", {"num_customer": num_customer})
    await turn("select_duration", {"duration_minutes": 60})
    await turn(
        "select_course",
        {"course_selection": CourseSelection(main_course=SERVICE)},
    )
    await turn("deny", {})
    await turn("select_time", {"start_time": time(10, 30)})
    if num_customer == 1:
        if therapist_preference is None:
            await turn("deny", {})
        else:
            await turn(
                "select_therapist",
                {"therapist_preference": therapist_preference},
            )
    else:
        await turn("deny", {})
    await turn("provide_phone", {"phone": "0901234567", "name": "Nguyen An"})
    await turn("confirm", {})
    return context, tuple(states)


def shop_response(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        request=request,
        json={
            "data": [
                {
                    "shop_id": str(SHOP.shop_id),
                    "shop_code": "SHOP001",
                    "name": SHOP.name,
                    "address": SHOP.address,
                    "phone": None,
                    "links": {
                        "self": f"/api/shops/{SHOP.shop_id}",
                        "courses": f"/api/shops/{SHOP.shop_id}/courses",
                        "available_slots": (
                            f"/api/shops/{SHOP.shop_id}/available-slots"
                        ),
                    },
                }
            ],
            "meta": {"total": 1, "limit": None, "next_cursor": None},
        },
    )


def settings() -> Settings:
    return Settings(pos_base_url="http://pos.test")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"llm_provider": "openrouter"}, "LLM_PROVIDER"),
        ({"gemini_model": "   "}, "GEMINI_MODEL"),
        ({"gemini_base_url": "https://example.test/openai/"}, "GEMINI_BASE_URL"),
        ({"llm_max_retries": 1}, "LLM_MAX_RETRIES"),
    ],
)
async def test_invalid_gemini_configuration_fails_fast(
    override: dict[str, object],
    message: str,
) -> None:
    configured = Settings(pos_base_url="http://pos.test", **override)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match=message):
        await create_application_container(configured)


@pytest.mark.asyncio
async def test_container_assembles_shared_dependencies_without_network_calls() -> None:
    request_count = 0

    def unexpected_request(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(500, request=request)

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(unexpected_request),
        base_url="http://pos.test",
    )
    container = await create_application_container(settings(), http_client=client)

    assert isinstance(container.booking_gateway, HTTPBookingGateway)
    gateway_handlers = tuple(
        handler
        for handler in container._handlers
        if not isinstance(handler, ConfirmPhoneHandler)
    )
    assert gateway_handlers
    assert all(
        handler._booking_gateway is container.booking_gateway  # type: ignore[attr-defined]
        for handler in gateway_handlers
    )
    assert REQUIRED_ACTIONS <= set(container.tool_bridge.registered_actions())
    assert container.state_machine._flow is container.flow_definition
    assert container.dialog_controller._flow is container.flow_definition
    assert container.dialog_controller._state_machine is container.state_machine
    assert container.dialog_controller._tool_bridge is container.tool_bridge
    assert isinstance(container.memory_cache, MemoryCache)
    assert container.conversation_context_store._cache is container.memory_cache
    assert container.instruction_builder.registered_templates()
    assert container.deterministic_nlu.parse(
        text="2 người",
        state=BookingState.SELECTING_PEOPLE,
    ).intent == "select_people"
    assert container.state_intent_policy.is_allowed(
        BookingState.SELECTING_PEOPLE,
        "select_people",
    )
    assert "*" not in container.state_intent_policy.allowed_for(BookingState.IDLE)
    assert container.entity_resolution_coordinator._search_shop_handler is (
        container._handlers[0]
    )
    assert container.entity_resolution_coordinator._search_service_handler is (
        container._handlers[1]
    )
    assert isinstance(container.llm_gateway, GeminiLLMGateway)
    assert container.llm_nlu_fallback._llm_gateway is container.llm_gateway
    assert container.llm_nlu_fallback._intent_policy is container.state_intent_policy
    assert container.faq_manager._knowledge_gateway is None
    assert container.faq_manager._instruction_builder is container.instruction_builder
    assert container.state_intent_policy.is_allowed(
        BookingState.IDLE,
        "ask_question",
    )
    assert container.state_intent_policy.is_allowed(
        BookingState.COMPLETED,
        "ask_question",
    )
    assert request_count == 0

    await container.close()
    assert not client.is_closed
    await client.aclose()


@pytest.mark.asyncio
async def test_two_containers_are_isolated_except_for_injected_client() -> None:
    client = httpx.AsyncClient()
    first = await create_application_container(settings(), http_client=client)
    second = await create_application_container(settings(), http_client=client)

    assert first.http_client is second.http_client
    assert first.booking_gateway is not second.booking_gateway
    assert first.dialog_controller is not second.dialog_controller
    assert first.tool_bridge is not second.tool_bridge
    assert first.state_machine is not second.state_machine
    assert first.flow_definition is not second.flow_definition
    assert first.memory_cache is not second.memory_cache
    assert first.conversation_context_store is not second.conversation_context_store
    assert first.conversation_context_store._cache is first.memory_cache
    assert second.conversation_context_store._cache is second.memory_cache
    assert first.instruction_builder is not second.instruction_builder
    assert first.deterministic_nlu is not second.deterministic_nlu
    assert first.state_intent_policy is not second.state_intent_policy
    assert (
        first.entity_resolution_coordinator
        is not second.entity_resolution_coordinator
    )
    assert first.llm_gateway is not second.llm_gateway
    assert first.llm_nlu_fallback is not second.llm_nlu_fallback
    assert first.faq_manager is not second.faq_manager
    assert first.llm_nlu_fallback._llm_gateway is first.llm_gateway
    assert second.llm_nlu_fallback._llm_gateway is second.llm_gateway

    async def custom_action(context: ActionExecutionContext) -> ActionResult:
        return ActionResult("container_only")

    first.tool_bridge.register_action("container_only", custom_action)
    first.instruction_builder.register_template(
        "container_only",
        lambda context, result: DialogResponseDraft("Chỉ container đầu."),
    )
    assert first.tool_bridge.has_action("container_only")
    assert not second.tool_bridge.has_action("container_only")
    assert first.instruction_builder.has_template("container_only")
    assert not second.instruction_builder.has_template("container_only")

    await first.close()
    await second.close()
    assert not client.is_closed
    await client.aclose()


@pytest.mark.asyncio
async def test_controller_reaches_people_state_with_only_one_shop_search() -> None:
    requests: list[httpx.Request] = []

    def handle_request(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET" and request.url.path == "/api/shops":
            return shop_response(request)
        return httpx.Response(500, request=request)

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handle_request),
        base_url="http://pos.test",
    )
    container = await create_application_container(settings(), http_client=client)
    context = BookingContext(conversation_id="conversation-1")

    start = await container.dialog_controller.handle_turn(
        context,
        DialogTurnInput(intent="start_booking", payload={}),
    )
    shop = await container.dialog_controller.handle_turn(
        context,
        DialogTurnInput(intent="select_store", payload={"shop": SHOP}),
    )
    booking_date = await container.dialog_controller.handle_turn(
        context,
        DialogTurnInput(
            intent="select_date",
            payload={"booking_date": date(2099, 8, 5)},
        ),
    )

    assert start.status is DialogTurnStatus.SUCCESS
    assert start.executed_actions == ("search_shop",)
    assert shop.status is DialogTurnStatus.SUCCESS
    assert shop.executed_actions == ("handle_store_selection",)
    assert booking_date.status is DialogTurnStatus.SUCCESS
    assert booking_date.executed_actions == ("handle_date_selection",)
    assert context.state is BookingState.SELECTING_PEOPLE
    assert context.shop is SHOP
    assert context.booking_date == date(2099, 8, 5)
    assert [(request.method, request.url.path) for request in requests] == [
        ("GET", "/api/shops")
    ]

    await container.close()
    await client.aclose()


@pytest.mark.asyncio
async def test_shop_search_failure_does_not_partially_mutate_context() -> None:
    requests: list[httpx.Request] = []

    def unavailable(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(503, request=request)

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(unavailable),
        base_url="http://pos.test",
    )
    container = await create_application_container(settings(), http_client=client)
    context = BookingContext(
        conversation_id="conversation-1",
        pending_action="keep",
    )

    result = await container.dialog_controller.handle_turn(
        context,
        DialogTurnInput(intent="start_booking", payload={}),
    )

    assert result.status is DialogTurnStatus.FAILURE_HANDLED
    assert result.instruction_template == "shop_lookup_unavailable"
    assert result.failed_action == "search_shop"
    assert context.state is BookingState.IDLE
    assert context.shop is None
    assert context.pending_action == "keep"
    assert len(requests) == 1

    await container.close()
    await client.aclose()


@pytest.mark.asyncio
async def test_phone_denial_uses_production_binding_and_commits_collection_state() -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(500, request=request)),
        base_url="http://pos.test",
    )
    container = await create_application_container(settings(), http_client=client)
    context = BookingContext(
        conversation_id="conversation-phone",
        state=BookingState.VERIFYING_PHONE,
        shop=SHOP,
        service=SERVICE,
        booking_date=date(2099, 8, 5),
        start_time=time(10, 30),
        num_customer=1,
        duration_minutes=60,
        phone="0901234567",
        phone_confirmed=True,
        ng_list_checked=True,
    )

    result = await container.dialog_controller.handle_turn(
        context,
        DialogTurnInput(intent="deny", payload={}),
    )

    assert result.status is DialogTurnStatus.SUCCESS
    assert result.executed_actions == ("clear_phone_confirmation",)
    assert context.state is BookingState.COLLECTING_PHONE
    assert context.phone is None
    assert context.shop is SHOP
    assert context.service == SERVICE
    assert context.start_time == time(10, 30)

    await container.close()
    await client.aclose()


@pytest.mark.asyncio
async def test_reload_failure_rolls_back_and_does_not_commit_selecting_time() -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(500, request=request)),
        base_url="http://pos.test",
    )
    container = await create_application_container(settings(), http_client=client)
    handler = FailingAvailabilityHandler()
    container.tool_bridge._check_availability_handler = handler
    stale_slots = (time(9, 0),)
    context = BookingContext(
        conversation_id="conversation-reload-failure",
        state=BookingState.BOOKING_FAILED,
        shop=SHOP,
        service=SERVICE,
        booking_date=date(2099, 8, 5),
        start_time=time(9, 0),
        num_customer=1,
        duration_minutes=60,
        available_slots=stale_slots,
    )

    result = await container.dialog_controller.handle_turn(
        context,
        DialogTurnInput(intent="select_time", payload={}),
    )

    assert result.status is DialogTurnStatus.FAILURE_UNHANDLED
    assert result.failed_action == "reload_time_slots"
    assert handler.calls == 1
    assert context.state is BookingState.BOOKING_FAILED
    assert context.available_slots == stale_slots
    assert context.start_time == time(9, 0)
    assert context.booking is None

    await container.close()
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("num_customer", "therapist_preference"),
    [
        (1, None),
        (1, TherapistPreference(TherapistPreferenceType.FEMALE)),
        (2, None),
        (3, None),
    ],
)
async def test_booking_happy_path_reaches_completed_once_without_user_code(
    monkeypatch: pytest.MonkeyPatch,
    num_customer: int,
    therapist_preference: TherapistPreference | None,
) -> None:
    gateway = RecordingBookingGateway()
    monkeypatch.setattr(dependencies, "HTTPBookingGateway", lambda **kwargs: gateway)
    client = httpx.AsyncClient(base_url="http://pos.test")
    container = await create_application_container(settings(), http_client=client)
    context, states = await advance_to_awaiting_confirmation(
        container,
        num_customer=num_customer,
        therapist_preference=therapist_preference,
    )

    result = await container.dialog_controller.handle_turn(
        context,
        DialogTurnInput(
            intent="confirm",
            payload={},
            idempotency_key=f"booking-{num_customer}",
        ),
    )
    response = container.instruction_builder.build_response(
        result=result,
        context=context,
    )

    assert states[:7] == (
        BookingState.SELECTING_SHOP,
        BookingState.SELECTING_DATE,
        BookingState.SELECTING_PEOPLE,
        BookingState.SELECTING_DURATION,
        BookingState.SELECTING_SERVICE,
        BookingState.SELECTING_SERVICE,
        BookingState.SELECTING_TIME,
    )
    assert BookingState.COLLECTING_PHONE in states
    assert states[-2:] == (
        BookingState.VERIFYING_PHONE,
        BookingState.AWAITING_CONFIRMATION,
    )
    assert result.status is DialogTurnStatus.SUCCESS
    assert result.executed_actions == ("create_booking",)
    assert context.state is BookingState.COMPLETED
    assert context.booking is not None
    assert context.reservation_code is None
    assert context.reservation_codes == ()
    assert "Đặt lịch thành công" in response.text
    assert "đã được ghi nhận" in response.text
    assert "Mã đặt lịch" not in response.text
    assert str(context.booking.booking_id) not in response.text
    assert all(
        str(child_id) not in response.text
        for child_id in context.child_reservation_ids
    )
    assert response.metadata == {"booking_created": True}
    assert len(gateway.final_requests) == 1
    assert len(gateway.create_requests) == 1
    assert len(context.child_reservation_ids) == num_customer
    assert gateway.create_requests[0].num_customer == num_customer
    if num_customer >= 2:
        expected = TherapistPreference(TherapistPreferenceType.NONE)
        assert context.therapist_preference == expected
        assert gateway.create_requests[0].therapist_preference == expected
    else:
        assert context.therapist_preference == (
            therapist_preference
            or TherapistPreference(TherapistPreferenceType.NONE)
        )

    await container.close()
    await client.aclose()


@pytest.mark.asyncio
async def test_final_denial_cancels_without_pos_create(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = RecordingBookingGateway()
    monkeypatch.setattr(dependencies, "HTTPBookingGateway", lambda **kwargs: gateway)
    client = httpx.AsyncClient(base_url="http://pos.test")
    container = await create_application_container(settings(), http_client=client)
    context, _ = await advance_to_awaiting_confirmation(
        container,
        num_customer=1,
        therapist_preference=None,
    )

    result = await container.dialog_controller.handle_turn(
        context,
        DialogTurnInput(intent="deny", payload={}),
    )

    assert result.status is DialogTurnStatus.SUCCESS
    assert context.state is BookingState.CANCELLED
    assert gateway.final_requests == []
    assert gateway.create_requests == []
    assert context.booking is None

    await container.close()
    await client.aclose()


@pytest.mark.asyncio
async def test_empty_availability_returns_to_date_without_selecting_a_slot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = RecordingBookingGateway()
    gateway.available_slots = ()
    monkeypatch.setattr(dependencies, "HTTPBookingGateway", lambda **kwargs: gateway)
    client = httpx.AsyncClient(base_url="http://pos.test")
    container = await create_application_container(settings(), http_client=client)
    context = BookingContext(
        conversation_id="e2e-no-slots",
        state=BookingState.SELECTING_SERVICE,
        shop=SHOP,
        booking_date=date(2099, 8, 5),
        num_customer=1,
        duration_minutes=60,
    )

    selected = await container.dialog_controller.handle_turn(
        context,
        DialogTurnInput(
            intent="select_course",
            payload={"course_selection": CourseSelection(main_course=SERVICE)},
        ),
    )

    assert selected.status is DialogTurnStatus.SUCCESS
    assert context.state is BookingState.SELECTING_SERVICE

    result = await container.dialog_controller.handle_turn(
        context,
        DialogTurnInput(intent="deny", payload={}),
    )

    assert result.status is DialogTurnStatus.FAILURE_HANDLED
    assert result.failure_code == "no_slots_available"
    assert context.state is BookingState.SELECTING_SERVICE
    assert context.booking_date == date(2099, 8, 5)
    assert context.service == SERVICE
    assert context.start_time is None
    assert context.available_slots is None
    assert gateway.create_requests == []

    await container.close()
    await client.aclose()


@pytest.mark.asyncio
async def test_time_selection_rejects_a_slot_outside_latest_availability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = RecordingBookingGateway()
    monkeypatch.setattr(dependencies, "HTTPBookingGateway", lambda **kwargs: gateway)
    client = httpx.AsyncClient(base_url="http://pos.test")
    container = await create_application_container(settings(), http_client=client)
    context = BookingContext(
        conversation_id="e2e-stale-slot",
        state=BookingState.SELECTING_TIME,
        shop=SHOP,
        service=SERVICE,
        booking_date=date(2099, 8, 5),
        num_customer=1,
        duration_minutes=60,
        available_slots=gateway.available_slots,
    )

    result = await container.dialog_controller.handle_turn(
        context,
        DialogTurnInput(intent="select_time", payload={"start_time": time(9, 0)}),
    )

    assert result.status is DialogTurnStatus.FAILURE_HANDLED
    assert result.failure_code == "slot_unavailable"
    assert context.state is BookingState.SELECTING_TIME
    assert context.start_time is None
    assert context.available_slots == gateway.available_slots
    assert gateway.create_requests == []

    await container.close()
    await client.aclose()


@pytest.mark.asyncio
async def test_create_failure_rolls_back_result_and_enters_recovery_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = RecordingBookingGateway(create_error=RuntimeError("POS unavailable"))
    monkeypatch.setattr(dependencies, "HTTPBookingGateway", lambda **kwargs: gateway)
    client = httpx.AsyncClient(base_url="http://pos.test")
    container = await create_application_container(settings(), http_client=client)
    context, _ = await advance_to_awaiting_confirmation(
        container,
        num_customer=1,
        therapist_preference=None,
    )

    result = await container.dialog_controller.handle_turn(
        context,
        DialogTurnInput(
            intent="confirm",
            payload={},
            idempotency_key="booking-failure",
        ),
    )

    assert result.status is DialogTurnStatus.FAILURE_HANDLED
    assert result.failure_code == "booking_api_error"
    assert result.failed_action == "create_booking"
    assert context.state is BookingState.BOOKING_FAILED
    assert context.booking is None
    assert context.booking_id is None
    assert context.reservation_code is None
    assert context.child_reservation_ids == ()
    assert len(gateway.final_requests) == 1
    assert len(gateway.create_requests) == 1

    await container.close()
    await client.aclose()


def accepts_booking_gateway(gateway: BookingGateway) -> BookingGateway:
    """Provide a static Protocol assignment checked by mypy."""
    return gateway


@pytest.mark.asyncio
async def test_http_gateway_satisfies_booking_gateway_protocol_statically() -> None:
    client = httpx.AsyncClient()
    gateway = HTTPBookingGateway(client=client, base_url="http://pos.test")

    assert accepts_booking_gateway(gateway) is gateway
    await client.aclose()
