"""Unit tests for DialogController message orchestration."""

import logging
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from datetime import time
from typing import cast
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.dependencies import ApplicationContainer
from app.dialog.dialog_controller import (
    DialogTurnInput,
    DialogTurnResult,
    DialogTurnStatus,
    _process_serialized_chat_message,
)
from app.dialog.instruction_builder import DialogResponse
from app.dialog.nlu import (
    EntityCandidate,
    EntityResolutionResult,
    EntityResolutionStatus,
    NLUEntityKind,
    NLUResolutionStatus,
    NLUResult,
    NLUSource,
    StateIntentPolicy,
)
from app.domain.booking_context import BookingContext
from app.domain.booking_models import Shop
from app.domain.booking_state import BookingState
from app.transport.chat_api import _to_chat_response
from app.transport.schemas import ChatRequest

SHOP = Shop(
    name="Shibuya",
    shop_id=UUID("11111111-1111-1111-1111-111111111111"),
)


class FakeStore:
    def __init__(self, context: BookingContext) -> None:
        self.context = context
        self.loaded_ids: list[str] = []
        self.saved: list[tuple[str, BookingContext]] = []

    @asynccontextmanager
    async def conversation_lock(
        self,
        conversation_id: str,
    ) -> AsyncIterator[None]:
        del conversation_id
        yield

    async def get_copy(self, conversation_id: str) -> BookingContext:
        self.loaded_ids.append(conversation_id)
        return self.context

    async def save(self, conversation_id: str, context: BookingContext) -> None:
        self.saved.append((conversation_id, context))


class FakeLLMNLU:
    def __init__(self, result: NLUResult) -> None:
        self.result = result
        self.calls: list[tuple[str, BookingState]] = []

    async def parse(
        self,
        *,
        text: str,
        state: BookingState,
        context: BookingContext | None = None,
    ) -> NLUResult:
        self.calls.append((text, state))
        return self.result


class FakeResolver:
    def __init__(self, result: EntityResolutionResult) -> None:
        self.result = result
        self.calls: list[tuple[NLUResult, BookingState, BookingContext]] = []

    async def resolve(
        self,
        *,
        nlu_result: NLUResult,
        state: BookingState,
        context: BookingContext,
    ) -> EntityResolutionResult:
        self.calls.append((nlu_result, state, context))
        return self.result


class FakeController:
    def __init__(self) -> None:
        self.calls: list[tuple[BookingContext, DialogTurnInput]] = []

    async def handle_turn(
        self,
        context: BookingContext,
        turn: DialogTurnInput,
    ) -> DialogTurnResult:
        self.calls.append((context, turn))
        return DialogTurnResult(
            status=DialogTurnStatus.SUCCESS,
            initial_state=context.state,
            final_state=context.state,
            intent=turn.intent,
            instruction_template="greeting",
            executed_actions=(),
            auto_transition_count=0,
        )


class FailedChangeController(FakeController):
    async def handle_turn(
        self,
        context: BookingContext,
        turn: DialogTurnInput,
    ) -> DialogTurnResult:
        self.calls.append((context, turn))
        return DialogTurnResult(
            status=DialogTurnStatus.FAILURE_HANDLED,
            initial_state=context.state,
            final_state=context.state,
            intent=turn.intent,
            instruction_template="change_invalid",
            executed_actions=(),
            auto_transition_count=0,
            failure_code="invalid_change",
        )


class StateChangingController(FakeController):
    async def handle_turn(
        self,
        context: BookingContext,
        turn: DialogTurnInput,
    ) -> DialogTurnResult:
        self.calls.append((context, turn))
        initial_state = context.state
        context.state = BookingState.SELECTING_SHOP
        return DialogTurnResult(
            status=DialogTurnStatus.SUCCESS,
            initial_state=initial_state,
            final_state=context.state,
            intent=turn.intent,
            instruction_template="greeting",
            executed_actions=(),
            auto_transition_count=0,
        )


class FakeBuilder:
    def __init__(self) -> None:
        self.calls: list[tuple[DialogTurnResult, BookingContext]] = []

    def build_response(
        self,
        *,
        result: DialogTurnResult,
        context: BookingContext,
    ) -> DialogResponse:
        self.calls.append((result, context))
        return DialogResponse(
            text="Safe response",
            instruction_template=result.instruction_template,
            state=result.final_state,
            status=result.status,
            metadata={"can_retry": True},
        )

    def build_faq_response(
        self,
        *,
        answer: str,
        source_count: int,
        context: BookingContext,
        handled_failure: bool = False,
    ) -> DialogResponse:
        status = DialogTurnStatus.FAILURE_HANDLED if handled_failure else DialogTurnStatus.SUCCESS
        return DialogResponse(
            text=answer,
            instruction_template=None,
            state=context.state,
            status=status,
            metadata={"response_type": "faq", "source_count": source_count},
        )


class FakeFAQManager:
    def __init__(self) -> None:
        self.calls: list[tuple[str, BookingContext]] = []

    async def answer(
        self,
        *,
        query: str,
        context: BookingContext,
    ) -> DialogResponse:
        self.calls.append((query, context))
        return DialogResponse(
            text="Cửa hàng mở cửa từ 09:00.",
            instruction_template=None,
            state=context.state,
            status=DialogTurnStatus.SUCCESS,
            metadata={"response_type": "faq", "source_count": 1},
        )


class FakeContainer:
    def __init__(
        self,
        *,
        context: BookingContext,
        nlu_result: NLUResult,
        resolution: EntityResolutionResult | None = None,
        faq_manager: FakeFAQManager | None = None,
    ) -> None:
        self.conversation_context_store = FakeStore(context)
        self.llm_nlu = FakeLLMNLU(nlu_result)
        self.entity_resolution_coordinator = FakeResolver(
            resolution or failed_resolution(NLUEntityKind.SHOP)
        )
        self.dialog_controller = FakeController()
        self.instruction_builder = FakeBuilder()
        self.faq_manager = faq_manager or FakeFAQManager()
        self.state_intent_policy = StateIntentPolicy(
            {
                BookingState.IDLE: frozenset({"start_booking", "ask_question"}),
                BookingState.SELECTING_SHOP: frozenset({"select_store", "ask_question"}),
                BookingState.AWAITING_CONFIRMATION: frozenset({"change_info", "ask_question"}),
            },
            frozenset(),
        )


def resolved_nlu() -> NLUResult:
    return NLUResult(
        intent="start_booking",
        payload={},
        confidence=1.0,
        source=NLUSource.LLM,
        resolution_status=NLUResolutionStatus.RESOLVED,
    )


def entity_nlu(kind: NLUEntityKind = NLUEntityKind.SHOP) -> NLUResult:
    return NLUResult(
        intent=None,
        payload={},
        confidence=0.8,
        source=NLUSource.LLM,
        resolution_status=NLUResolutionStatus.ENTITY_RESOLUTION_REQUIRED,
        entity_query="Shibuya",
        entity_kind=kind,
    )


def unresolved_nlu() -> NLUResult:
    return NLUResult(
        intent=None,
        payload={},
        confidence=0.0,
        source=NLUSource.LLM,
        resolution_status=NLUResolutionStatus.UNRESOLVED,
    )


def greeting_nlu() -> NLUResult:
    return NLUResult(
        intent="greeting",
        payload={},
        confidence=1.0,
        source=NLUSource.LLM,
        resolution_status=NLUResolutionStatus.RESOLVED,
    )


def change_nlu() -> NLUResult:
    return NLUResult(
        intent="change_info",
        payload={"change_target": "people", "num_customer": 5},
        confidence=1.0,
        source=NLUSource.LLM,
        resolution_status=NLUResolutionStatus.RESOLVED,
        matched_rule="change_booking_field",
    )


def generic_change_nlu() -> NLUResult:
    return NLUResult(
        intent="change_info",
        payload={},
        confidence=1.0,
        source=NLUSource.LLM,
        resolution_status=NLUResolutionStatus.RESOLVED,
        matched_rule="change_booking_field",
    )


def faq_nlu(query: str) -> NLUResult:
    return NLUResult(
        intent="ask_question",
        payload={"query": query},
        confidence=1.0,
        source=NLUSource.LLM,
        resolution_status=NLUResolutionStatus.RESOLVED,
        matched_rule="faq_explicit",
    )


def failed_resolution(kind: NLUEntityKind) -> EntityResolutionResult:
    return EntityResolutionResult(
        status=EntityResolutionStatus.FAILED,
        entity_kind=kind,
        dispatch_intent=None,
        dispatch_payload={},
        failure_code="resolution_unavailable",
    )


def request(*, idempotency_key: str | None = None) -> ChatRequest:
    return ChatRequest(
        conversation_id="conversation-a",
        message="Tôi muốn đặt lịch",
        idempotency_key=idempotency_key,
    )


def as_container(fake: FakeContainer) -> ApplicationContainer:
    return cast(ApplicationContainer, fake)


async def _process_controller_pipeline(
    *,
    request: ChatRequest,
    container: ApplicationContainer,
    correlation_id: str | None = None,
) -> DialogResponse:
    return await _process_serialized_chat_message(
        conversation_id=request.conversation_id,
        message=request.message,
        idempotency_key=request.idempotency_key,
        container=container,
        correlation_id=correlation_id,
    )


@pytest.mark.asyncio
async def test_resolved_branch_runs_controller_renderer_and_save_once() -> None:
    context = BookingContext("conversation-a")
    fake = FakeContainer(context=context, nlu_result=resolved_nlu())

    response = await _process_controller_pipeline(
        request=request(idempotency_key=" stable-key "),
        container=as_container(fake),
    )

    assert fake.conversation_context_store.loaded_ids == ["conversation-a"]
    assert fake.entity_resolution_coordinator.calls == []
    assert fake.llm_nlu.calls == [("Tôi muốn đặt lịch", BookingState.IDLE)]
    assert len(fake.dialog_controller.calls) == 1
    assert fake.dialog_controller.calls[0][1].idempotency_key == " stable-key "
    assert len(fake.instruction_builder.calls) == 1
    assert fake.conversation_context_store.saved == [("conversation-a", context)]
    assert response.text == "Safe response"


@pytest.mark.asyncio
async def test_fresh_context_greeting_does_not_claim_booking_is_preserved() -> None:
    context = BookingContext("conversation-a")
    fake = FakeContainer(context=context, nlu_result=greeting_nlu())

    response = await _process_controller_pipeline(
        request=ChatRequest(conversation_id="conversation-a", message="xin chào"),
        container=as_container(fake),
    )

    assert "Thông tin đặt lịch hiện tại" not in response.text
    assert "đặt lịch" in response.text
    assert context.state is BookingState.IDLE


@pytest.mark.asyncio
async def test_meaningful_context_greeting_mentions_booking_is_preserved() -> None:
    context = BookingContext(
        "conversation-a",
        state=BookingState.SELECTING_DURATION,
        shop=SHOP,
    )
    fake = FakeContainer(context=context, nlu_result=greeting_nlu())

    response = await _process_controller_pipeline(
        request=ChatRequest(conversation_id="conversation-a", message="xin chào"),
        container=as_container(fake),
    )

    assert "Thông tin đặt lịch hiện tại của bạn vẫn được giữ" in response.text
    assert context.state is BookingState.SELECTING_DURATION
    assert context.shop == SHOP


@pytest.mark.asyncio
async def test_greeting_with_reused_looking_but_empty_context_stays_fresh() -> None:
    context = BookingContext("conversation-reused")
    fake = FakeContainer(context=context, nlu_result=greeting_nlu())

    response = await _process_controller_pipeline(
        request=ChatRequest(conversation_id="conversation-reused", message="xin chào"),
        container=as_container(fake),
    )

    assert "Thông tin đặt lịch hiện tại" not in response.text
    assert context.state is BookingState.IDLE


@pytest.mark.asyncio
async def test_turn_trace_logs_lifecycle_intent_transition_without_raw_content(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOG_USER_MESSAGES", "false")
    monkeypatch.setenv("LOG_LLM_PROMPTS", "false")
    fake = FakeContainer(
        context=BookingContext("private-conversation-id"),
        nlu_result=resolved_nlu(),
    )
    chat_request = ChatRequest(
        conversation_id="private-conversation-id",
        message="private raw user message 0901234567",
    )

    with caplog.at_level(logging.INFO, logger="app.dialog.dialog_controller"):
        await _process_controller_pipeline(
            request=chat_request,
            container=as_container(fake),
        )

    output = caplog.text
    assert "[[1] REQUEST #1] request_started" in output
    assert "emitter=app/dialog/dialog_controller.py :: _process_serialized_chat_message()" in output
    assert "[[2] CONTEXT #1] loaded" in output
    assert "emitter=app/dialog/dialog_controller.py :: _trace_context_loaded()" in output
    assert "caller=ConversationContextStore.get_copy()" in output
    assert "turn_failed" not in output
    assert "[[5] ROUTING #1] dispatch" in output
    assert "emitter=app/dialog/dialog_controller.py :: _trace_route()" in output
    assert "caller=_process_bound_chat_message()" in output
    assert "[[5] ROUTING #1] state_actions_completed" in output
    assert "emitter=app/dialog/dialog_controller.py :: _process_bound_chat_message()" in output
    assert "[[8] CONTEXT SAVE #1] saved" in output
    assert "emitter=app/dialog/dialog_controller.py :: _trace_context_saved()" in output
    assert "caller=ConversationContextStore.save()" in output
    assert "[[7] RESPONSE #1] response_ready" in output
    assert "instruction_template=greeting" in output
    assert "private-conversation-id" not in output
    assert "private raw user message" not in output
    assert "0901234567" not in output
    assert "Safe response" in output


@pytest.mark.asyncio
async def test_turn_trace_sequence_increments_for_same_conversation(
    caplog: pytest.LogCaptureFixture,
) -> None:
    context = BookingContext("conversation-a")
    fake = FakeContainer(context=context, nlu_result=resolved_nlu())

    with caplog.at_level(logging.INFO, logger="app.dialog.dialog_controller"):
        await _process_controller_pipeline(request=request(), container=as_container(fake))
        await _process_controller_pipeline(request=request(), container=as_container(fake))

    assert "[[1] REQUEST #1] request_started" in caplog.text
    assert "[[1] REQUEST #2] request_started" in caplog.text
    assert context.turn_sequence == 2


@pytest.mark.asyncio
async def test_local_raw_turn_text_flags_log_truncated_user_and_assistant(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("LOG_USER_MESSAGES", "true")
    monkeypatch.setenv("LOG_AI_MESSAGES", "true")
    fake = FakeContainer(
        context=BookingContext("conversation-a"),
        nlu_result=resolved_nlu(),
    )
    fake.dialog_controller = StateChangingController()
    raw_message = "u" * 510

    with caplog.at_level(logging.DEBUG, logger="app.dialog.dialog_controller"):
        await _process_controller_pipeline(
            request=ChatRequest(conversation_id="conversation-a", message=raw_message),
            container=as_container(fake),
            correlation_id="request-correlation-a",
        )

    assert f"user_message={'u' * 500}" in caplog.text
    assert "u" * 501 not in caplog.text
    assert "assistant_message=Safe response" in caplog.text
    assert "[[8] CONTEXT SAVE #1] saved" in caplog.text
    assert "'state': 'selecting_shop'" in caplog.text
    assert caplog.text.count("correlation=") > 3
    correlations = {
        getattr(record, "correlation", None)
        for record in caplog.records
        if getattr(record, "component", None)
    }
    assert len(correlations) == 1


@pytest.mark.asyncio
async def test_production_never_logs_raw_turn_text_when_flags_are_true(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("LOG_USER_MESSAGES", "true")
    monkeypatch.setenv("LOG_AI_MESSAGES", "true")
    fake = FakeContainer(
        context=BookingContext("conversation-a"),
        nlu_result=resolved_nlu(),
    )

    with caplog.at_level(logging.DEBUG, logger="app.dialog.dialog_controller"):
        await _process_controller_pipeline(
            request=ChatRequest(
                conversation_id="conversation-a",
                message="production private message",
            ),
            container=as_container(fake),
        )

    assert "production private message" not in caplog.text
    assert "[[7] RESPONSE #1] response_ready" in caplog.text


@pytest.mark.asyncio
async def test_entity_resolved_branch_runs_resolver_controller_renderer_and_save() -> None:
    resolution = EntityResolutionResult(
        status=EntityResolutionStatus.RESOLVED,
        entity_kind=NLUEntityKind.SHOP,
        dispatch_intent="select_store",
        dispatch_payload={"shop": SHOP},
        matched_count=1,
    )
    context = BookingContext("conversation-a", state=BookingState.SELECTING_SHOP)
    fake = FakeContainer(
        context=context,
        nlu_result=entity_nlu(),
        resolution=resolution,
    )

    await _process_controller_pipeline(
        request=request(idempotency_key="key"),
        container=as_container(fake),
    )

    assert len(fake.entity_resolution_coordinator.calls) == 1
    assert fake.llm_nlu.calls == [(request().message, BookingState.SELECTING_SHOP)]
    assert len(fake.dialog_controller.calls) == 1
    turn = fake.dialog_controller.calls[0][1]
    assert turn.payload == {"shop": SHOP}
    assert turn.idempotency_key == "key"
    assert len(fake.instruction_builder.calls) == 1
    assert fake.conversation_context_store.saved == [("conversation-a", context)]


@pytest.mark.asyncio
async def test_valid_llm_result_runs_one_controller_turn() -> None:
    context = BookingContext("conversation-a")
    fake = FakeContainer(
        context=context,
        nlu_result=resolved_nlu(),
    )

    response = await _process_controller_pipeline(
        request=request(),
        container=as_container(fake),
    )

    assert len(fake.llm_nlu.calls) == 1
    assert len(fake.dialog_controller.calls) == 1
    assert len(fake.instruction_builder.calls) == 1
    assert fake.conversation_context_store.saved == [("conversation-a", context)]
    assert response.text == "Safe response"


@pytest.mark.asyncio
async def test_every_turn_calls_llm_nlu_once() -> None:
    context = BookingContext("conversation-a")
    fake = FakeContainer(
        context=context,
        nlu_result=resolved_nlu(),
    )

    response = await _process_controller_pipeline(request=request(), container=as_container(fake))

    assert fake.llm_nlu.calls == [(request().message, BookingState.IDLE)]
    assert response.text == "Safe response"


@pytest.mark.asyncio
async def test_faq_branch_uses_knowledge_without_controller_resolver_or_save() -> None:
    query = "Cửa hàng mở cửa lúc mấy giờ?"
    faq_manager = FakeFAQManager()
    context = BookingContext("conversation-a", state=BookingState.SELECTING_SHOP)
    fake = FakeContainer(
        context=context,
        nlu_result=faq_nlu(query),
        faq_manager=faq_manager,
    )

    response = await _process_controller_pipeline(request=request(), container=as_container(fake))

    assert faq_manager.calls == [(query, context)]
    assert response.text == "Cửa hàng mở cửa từ 09:00."
    assert response.state is BookingState.SELECTING_SHOP
    assert response.metadata == {"response_type": "faq", "source_count": 1}
    assert fake.entity_resolution_coordinator.calls == []
    assert fake.dialog_controller.calls == []
    assert fake.conversation_context_store.saved == [("conversation-a", context)]


@pytest.mark.asyncio
async def test_ambiguous_branch_returns_ordered_limited_safe_candidate_names() -> None:
    candidates = tuple(
        EntityCandidate(
            kind=NLUEntityKind.SHOP,
            display_name="Shop 1" if index in {1, 2} else f"Shop {index}",
            selection_key=f"shop:{index}",
        )
        for index in range(10)
    )
    resolution = EntityResolutionResult(
        status=EntityResolutionStatus.AMBIGUOUS,
        entity_kind=NLUEntityKind.SHOP,
        dispatch_intent=None,
        dispatch_payload={},
        candidates=candidates,
        matched_count=len(candidates),
    )
    fake = FakeContainer(
        context=BookingContext("conversation-a", state=BookingState.SELECTING_SHOP),
        nlu_result=entity_nlu(),
        resolution=resolution,
    )

    response = await _process_controller_pipeline(request=request(), container=as_container(fake))

    assert response.quick_replies == (
        "Shop 0",
        "Shop 1",
        "Shop 3",
        "Shop 4",
        "Shop 5",
        "Shop 6",
        "Shop 7",
        "Shop 8",
    )
    assert all("shop:" not in value for value in response.quick_replies)
    assert fake.dialog_controller.calls == []
    assert len(fake.conversation_context_store.saved) == 1


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        (NLUEntityKind.SHOP, "Không tìm thấy cửa hàng phù hợp"),
        (NLUEntityKind.COURSE, "Không tìm thấy liệu trình phù hợp"),
        (NLUEntityKind.THERAPIST, "Không tìm thấy kỹ thuật viên phù hợp"),
    ],
)
@pytest.mark.asyncio
async def test_not_found_branch_is_kind_specific_without_dispatch(
    kind: NLUEntityKind,
    expected: str,
) -> None:
    resolution = EntityResolutionResult(
        EntityResolutionStatus.NOT_FOUND,
        kind,
        None,
        {},
        failure_code="not_found",
    )
    fake = FakeContainer(
        context=BookingContext("conversation-a"),
        nlu_result=entity_nlu(kind),
        resolution=resolution,
    )

    response = await _process_controller_pipeline(request=request(), container=as_container(fake))

    assert expected in response.text
    assert fake.dialog_controller.calls == []
    assert len(fake.conversation_context_store.saved) == 1


@pytest.mark.asyncio
async def test_unsupported_therapist_returns_guidance_without_controller() -> None:
    resolution = EntityResolutionResult(
        EntityResolutionStatus.UNSUPPORTED,
        NLUEntityKind.THERAPIST,
        None,
        {},
        failure_code="therapist_lookup_not_supported",
    )
    fake = FakeContainer(
        context=BookingContext("conversation-a"),
        nlu_result=entity_nlu(NLUEntityKind.THERAPIST),
        resolution=resolution,
    )

    response = await _process_controller_pipeline(request=request(), container=as_container(fake))

    assert "Nam, Nữ hoặc Không yêu cầu" in response.text
    assert fake.dialog_controller.calls == []


@pytest.mark.asyncio
async def test_failed_resolution_returns_generic_text_without_retry_or_raw_error() -> None:
    fake = FakeContainer(
        context=BookingContext("conversation-a"),
        nlu_result=entity_nlu(),
        resolution=failed_resolution(NLUEntityKind.SHOP),
    )

    response = await _process_controller_pipeline(request=request(), container=as_container(fake))

    assert response.text == "Hệ thống chưa thể tra cứu thông tin lúc này. Vui lòng thử lại."
    assert "resolution_unavailable" not in response.text
    assert len(fake.entity_resolution_coordinator.calls) == 1
    assert fake.dialog_controller.calls == []
    assert len(fake.conversation_context_store.saved) == 1


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (BookingState.IDLE, "Tôi muốn đặt lịch"),
        (BookingState.SELECTING_PEOPLE, "số người từ 1 đến 3"),
        (BookingState.COMPLETED, "nhập lại rõ hơn"),
    ],
)
@pytest.mark.asyncio
async def test_unresolved_branch_is_state_aware_and_does_not_dispatch(
    state: BookingState,
    expected: str,
) -> None:
    fake = FakeContainer(
        context=BookingContext("conversation-a", state=state),
        nlu_result=unresolved_nlu(),
    )

    response = await _process_controller_pipeline(request=request(), container=as_container(fake))

    assert expected in response.text
    assert response.state is state
    assert fake.llm_nlu.calls == [(request().message, state)]
    assert fake.entity_resolution_coordinator.calls == []
    assert fake.dialog_controller.calls == []
    assert len(fake.conversation_context_store.saved) == 1


@pytest.mark.parametrize(
    ("state", "expected_replies"),
    [
        (BookingState.IDLE, ("Tôi muốn đặt lịch", "Xem danh sách cửa hàng")),
        (BookingState.SELECTING_DATE, ("Hôm nay", "Ngày mai")),
        (BookingState.SELECTING_PEOPLE, ("1 người", "2 người", "3 người")),
        (
            BookingState.SELECTING_DURATION,
            ("45 phút", "60 phút", "90 phút"),
        ),
        (
            BookingState.VERIFYING_PHONE,
            ("Xác nhận", "Nhập lại"),
        ),
        (
            BookingState.AWAITING_CONFIRMATION,
            ("Xác nhận", "Chỉnh sửa", "Hủy"),
        ),
    ],
)
@pytest.mark.asyncio
async def test_unresolved_booking_input_suggests_valid_next_actions(
    state: BookingState,
    expected_replies: tuple[str, ...],
) -> None:
    fake = FakeContainer(
        context=BookingContext("conversation-a", state=state),
        nlu_result=unresolved_nlu(),
    )

    response = await _process_controller_pipeline(request=request(), container=as_container(fake))

    assert response.quick_replies == expected_replies
    assert response.state is state


@pytest.mark.asyncio
async def test_unresolved_time_only_suggests_latest_validated_slots() -> None:
    context = BookingContext(
        "conversation-a",
        state=BookingState.SELECTING_TIME,
        available_slots=(time(9, 0), time(10, 30)),
    )
    fake = FakeContainer(context=context, nlu_result=unresolved_nlu())

    response = await _process_controller_pipeline(request=request(), container=as_container(fake))

    assert response.quick_replies == ("09:00", "10:30")


@pytest.mark.asyncio
async def test_failed_change_is_rendered_without_saving_partial_context() -> None:
    context = BookingContext(
        "conversation-a",
        state=BookingState.AWAITING_CONFIRMATION,
        num_customer=1,
    )
    fake = FakeContainer(context=context, nlu_result=change_nlu())
    fake.dialog_controller = FailedChangeController()

    response = await _process_controller_pipeline(request=request(), container=as_container(fake))

    assert response.status is DialogTurnStatus.FAILURE_HANDLED
    assert context.num_customer == 1
    assert len(fake.dialog_controller.calls) == 1
    assert fake.conversation_context_store.saved == [("conversation-a", context)]


@pytest.mark.asyncio
async def test_generic_change_request_returns_change_menu_without_dispatching_turn() -> None:
    context = BookingContext(
        "conversation-a",
        state=BookingState.AWAITING_CONFIRMATION,
    )
    fake = FakeContainer(context=context, nlu_result=generic_change_nlu())

    response = await _process_controller_pipeline(request=request(), container=as_container(fake))

    assert fake.dialog_controller.calls == []
    assert response.state is BookingState.AWAITING_CONFIRMATION
    assert response.quick_replies == (
        "Đổi cửa hàng",
        "Đổi ngày",
        "Đổi số người",
        "Đổi thời lượng",
        "Đổi liệu trình",
        "Đổi giờ",
        "Đổi kỹ thuật viên",
        "Đổi số điện thoại",
    )
    assert "Bạn muốn chỉnh sửa thông tin nào?" in response.text


def test_request_validation_trims_only_contract_fields() -> None:
    parsed = ChatRequest(
        conversation_id="  conversation-a  ",
        message="  Xin Chào  ",
        idempotency_key=" stable-key ",
    )

    assert parsed.conversation_id == "conversation-a"
    assert parsed.message == "Xin Chào"
    assert parsed.idempotency_key == " stable-key "


@pytest.mark.parametrize(
    "payload",
    [
        {"conversation_id": " ", "message": "hello"},
        {"conversation_id": "conversation-a", "message": " "},
        {"conversation_id": "conversation-a", "message": "x" * 2001},
        {
            "conversation_id": "conversation-a",
            "message": "hello",
            "idempotency_key": "",
        },
    ],
)
def test_request_validation_rejects_invalid_payloads(payload: Mapping[str, object]) -> None:
    with pytest.raises(ValidationError):
        ChatRequest.model_validate(payload)


def test_response_mapping_copies_only_ui_safe_fields() -> None:
    response = DialogResponse(
        text="Safe response",
        instruction_template="ask_shop",
        state=BookingState.SELECTING_SHOP,
        status=DialogTurnStatus.SUCCESS,
        quick_replies=("Shibuya",),
        metadata={"can_retry": True, "private": "must-not-leak"},
    )

    mapped = _to_chat_response("conversation-a", response)

    assert mapped.conversation_id == "conversation-a"
    assert mapped.text == "Safe response"
    assert mapped.quick_replies == ["Shibuya"]
    assert mapped.metadata == {"can_retry": True}
