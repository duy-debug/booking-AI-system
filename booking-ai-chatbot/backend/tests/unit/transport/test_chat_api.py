"""Unit tests for deterministic chat-message orchestration."""

from collections.abc import Mapping
from typing import cast
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.dependencies import ApplicationContainer
from app.dialog.dialog_controller import (
    DialogTurnInput,
    DialogTurnResult,
    DialogTurnStatus,
)
from app.dialog.entity_resolution import (
    EntityCandidate,
    EntityResolutionResult,
    EntityResolutionStatus,
)
from app.dialog.instruction_builder import DialogResponse
from app.dialog.nlu import (
    NLUEntityKind,
    NLUResolutionStatus,
    NLUResult,
    NLUSource,
    StateIntentPolicy,
)
from app.domain.booking import Shop
from app.domain.booking_context import BookingContext
from app.domain.booking_state import BookingState
from app.transport.chat_api import _process_chat_message, _to_chat_response
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

    async def get_or_create(self, conversation_id: str) -> BookingContext:
        self.loaded_ids.append(conversation_id)
        return self.context

    async def save(self, conversation_id: str, context: BookingContext) -> None:
        self.saved.append((conversation_id, context))


class FakeNLU:
    def __init__(self, result: NLUResult) -> None:
        self.result = result
        self.calls: list[tuple[str, BookingState]] = []

    def parse(self, *, text: str, state: BookingState) -> NLUResult:
        self.calls.append((text, state))
        return self.result


class FakeLLMFallback:
    def __init__(self, result: NLUResult) -> None:
        self.result = result
        self.calls: list[tuple[str, BookingState]] = []

    async def parse(self, *, text: str, state: BookingState) -> NLUResult:
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


class FakeContainer:
    def __init__(
        self,
        *,
        context: BookingContext,
        nlu_result: NLUResult,
        resolution: EntityResolutionResult | None = None,
        llm_result: NLUResult | None = None,
    ) -> None:
        self.conversation_context_store = FakeStore(context)
        self.deterministic_nlu = FakeNLU(nlu_result)
        self.llm_nlu_fallback = FakeLLMFallback(llm_result or unresolved_nlu())
        self.entity_resolution_coordinator = FakeResolver(
            resolution or failed_resolution(NLUEntityKind.SHOP)
        )
        self.dialog_controller = FakeController()
        self.instruction_builder = FakeBuilder()
        self.state_intent_policy = StateIntentPolicy(
            {
                BookingState.IDLE: frozenset({"start_booking"}),
                BookingState.SELECTING_SHOP: frozenset({"select_store"}),
            },
            frozenset(),
        )


def resolved_nlu() -> NLUResult:
    return NLUResult(
        intent="start_booking",
        payload={},
        confidence=1.0,
        source=NLUSource.DETERMINISTIC,
        resolution_status=NLUResolutionStatus.RESOLVED,
    )


def entity_nlu(kind: NLUEntityKind = NLUEntityKind.SHOP) -> NLUResult:
    return NLUResult(
        intent=None,
        payload={},
        confidence=0.8,
        source=NLUSource.DETERMINISTIC,
        resolution_status=NLUResolutionStatus.ENTITY_RESOLUTION_REQUIRED,
        entity_query="Shibuya",
        entity_kind=kind,
    )


def unresolved_nlu() -> NLUResult:
    return NLUResult(
        intent=None,
        payload={},
        confidence=0.0,
        source=NLUSource.FALLBACK,
        resolution_status=NLUResolutionStatus.UNRESOLVED,
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


@pytest.mark.asyncio
async def test_resolved_branch_runs_controller_renderer_and_save_once() -> None:
    context = BookingContext("conversation-a")
    fake = FakeContainer(context=context, nlu_result=resolved_nlu())

    response = await _process_chat_message(
        request=request(idempotency_key=" stable-key "),
        container=as_container(fake),
    )

    assert fake.conversation_context_store.loaded_ids == ["conversation-a"]
    assert fake.deterministic_nlu.calls == [("Tôi muốn đặt lịch", BookingState.IDLE)]
    assert fake.entity_resolution_coordinator.calls == []
    assert fake.llm_nlu_fallback.calls == []
    assert len(fake.dialog_controller.calls) == 1
    assert fake.dialog_controller.calls[0][1].idempotency_key == " stable-key "
    assert fake.dialog_controller.calls[0][1].raw_message == "Tôi muốn đặt lịch"
    assert len(fake.instruction_builder.calls) == 1
    assert fake.conversation_context_store.saved == [("conversation-a", context)]
    assert response.text == "Safe response"


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

    await _process_chat_message(
        request=request(idempotency_key="key"),
        container=as_container(fake),
    )

    assert len(fake.entity_resolution_coordinator.calls) == 1
    assert fake.llm_nlu_fallback.calls == []
    assert len(fake.dialog_controller.calls) == 1
    turn = fake.dialog_controller.calls[0][1]
    assert turn.payload == {"shop": SHOP}
    assert turn.idempotency_key == "key"
    assert len(fake.instruction_builder.calls) == 1
    assert fake.conversation_context_store.saved == [("conversation-a", context)]


@pytest.mark.asyncio
async def test_unresolved_deterministic_result_uses_one_valid_llm_result() -> None:
    context = BookingContext("conversation-a")
    fake = FakeContainer(
        context=context,
        nlu_result=unresolved_nlu(),
        llm_result=resolved_nlu(),
    )

    response = await _process_chat_message(
        request=request(),
        container=as_container(fake),
    )

    assert len(fake.deterministic_nlu.calls) == 1
    assert len(fake.llm_nlu_fallback.calls) == 1
    assert len(fake.dialog_controller.calls) == 1
    assert len(fake.instruction_builder.calls) == 1
    assert fake.conversation_context_store.saved == [("conversation-a", context)]
    assert response.text == "Safe response"


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

    response = await _process_chat_message(request=request(), container=as_container(fake))

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
    assert fake.conversation_context_store.saved == []


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

    response = await _process_chat_message(request=request(), container=as_container(fake))

    assert expected in response.text
    assert fake.dialog_controller.calls == []
    assert fake.conversation_context_store.saved == []


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

    response = await _process_chat_message(request=request(), container=as_container(fake))

    assert "Nam, Nữ hoặc Không yêu cầu" in response.text
    assert fake.dialog_controller.calls == []


@pytest.mark.asyncio
async def test_failed_resolution_returns_generic_text_without_retry_or_raw_error() -> None:
    fake = FakeContainer(
        context=BookingContext("conversation-a"),
        nlu_result=entity_nlu(),
        resolution=failed_resolution(NLUEntityKind.SHOP),
    )

    response = await _process_chat_message(request=request(), container=as_container(fake))

    assert response.text == "Hệ thống chưa thể tra cứu thông tin lúc này. Vui lòng thử lại."
    assert "resolution_unavailable" not in response.text
    assert len(fake.entity_resolution_coordinator.calls) == 1
    assert fake.dialog_controller.calls == []
    assert fake.conversation_context_store.saved == []


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

    response = await _process_chat_message(request=request(), container=as_container(fake))

    assert expected in response.text
    assert response.state is state
    assert fake.llm_nlu_fallback.calls == [(request().message, state)]
    assert fake.entity_resolution_coordinator.calls == []
    assert fake.dialog_controller.calls == []
    assert fake.conversation_context_store.saved == []


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
        quick_replies=("A", "B"),
        metadata={"can_retry": True, "phone": "0901234567"},
    )

    mapped = _to_chat_response("conversation-a", response)

    assert mapped.model_dump() == {
        "conversation_id": "conversation-a",
        "text": "Safe response",
        "state": "selecting_shop",
        "status": "success",
        "instruction_template": "ask_shop",
        "quick_replies": ["A", "B"],
        "metadata": {"can_retry": True},
    }
