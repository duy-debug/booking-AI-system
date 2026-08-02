"""Unit tests for structured, state-aware LLM NLU fallback."""

import asyncio
import json
from datetime import date, time

import pytest

from app.application.ports.llm_gateway import (
    LLMGatewayUnavailableError,
    LLMMessage,
    LLMResponse,
)
from app.dialog.nlu import (
    LLMNLUFallback,
    NLUEntityKind,
    NLUResolutionStatus,
    NLUSource,
    StateIntentPolicy,
)
from app.domain.booking_state import BookingState


class FakeLLMGateway:
    def __init__(
        self,
        response: LLMResponse | None = None,
        error: BaseException | None = None,
    ) -> None:
        self.response = response or LLMResponse()
        self.error = error
        self.calls = 0
        self.messages: list[LLMMessage] = []

    async def generate(
        self,
        messages: list[LLMMessage],
        *,
        tools: list[dict[str, object]] | None = None,
    ) -> LLMResponse:
        self.calls += 1
        self.messages = messages
        if self.error is not None:
            raise self.error
        return self.response


def policy() -> StateIntentPolicy:
    return StateIntentPolicy(
        {
            BookingState.IDLE: frozenset({"start_booking", "unknown"}),
            BookingState.SELECTING_SHOP: frozenset({"select_store", "unknown"}),
            BookingState.SELECTING_DATE: frozenset({"select_date", "unknown"}),
            BookingState.SELECTING_PEOPLE: frozenset({"select_people", "unknown"}),
            BookingState.SELECTING_DURATION: frozenset(
                {"select_duration", "unknown"}
            ),
            BookingState.SELECTING_SERVICE: frozenset({"select_course", "unknown"}),
            BookingState.SELECTING_TIME: frozenset({"select_time", "unknown"}),
            BookingState.SELECTING_THERAPIST: frozenset(
                {"select_therapist", "deny", "unknown"}
            ),
            BookingState.COLLECTING_PHONE: frozenset({"provide_phone", "unknown"}),
            BookingState.AWAITING_CONFIRMATION: frozenset(
                {"confirm", "deny", "change_info", "unknown"}
            ),
        },
        frozenset(),
    )


def structured(
    *,
    intent: str,
    confidence: float = 0.9,
    entities: dict[str, object] | None = None,
    entity_kind: str | None = None,
    entity_query: str | None = None,
    **extra: object,
) -> str:
    return json.dumps(
        {
            "intent": intent,
            "confidence": confidence,
            "entities": entities or {},
            "entity_kind": entity_kind,
            "entity_query": entity_query,
            **extra,
        }
    )


def fallback_for(content: str, *, min_confidence: float = 0.7) -> tuple[
    LLMNLUFallback,
    FakeLLMGateway,
]:
    gateway = FakeLLMGateway(LLMResponse(content=content))
    return (
        LLMNLUFallback(
            llm_gateway=gateway,
            intent_policy=policy(),
            min_confidence=min_confidence,
        ),
        gateway,
    )


@pytest.mark.asyncio
async def test_valid_people_output_maps_to_typed_nlu_result() -> None:
    fallback, gateway = fallback_for(
        structured(intent="select_people", entities={"number_of_people": 3})
    )

    result = await fallback.parse(
        text="Mai tôi đi cùng hai người bạn",
        state=BookingState.SELECTING_PEOPLE,
    )

    assert result.resolution_status is NLUResolutionStatus.RESOLVED
    assert result.intent == "select_people"
    assert result.payload == {"num_customer": 3}
    assert type(result.payload["num_customer"]) is int
    assert result.source is NLUSource.FALLBACK
    assert result.confidence == 0.9
    assert gateway.calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("state", "intent", "entities", "expected"),
    [
        (
            BookingState.SELECTING_DURATION,
            "select_duration",
            {"duration_minutes": 60},
            {"duration_minutes": 60},
        ),
        (
            BookingState.SELECTING_DATE,
            "select_date",
            {"booking_date": "2026-08-03"},
            {"booking_date": date(2026, 8, 3)},
        ),
        (
            BookingState.SELECTING_TIME,
            "select_time",
            {"start_time": "19:00"},
            {"start_time": time(19, 0)},
        ),
    ],
)
async def test_supported_primitive_entities_map_to_domain_neutral_payload_types(
    state: BookingState,
    intent: str,
    entities: dict[str, object],
    expected: dict[str, object],
) -> None:
    fallback, _ = fallback_for(structured(intent=intent, entities=entities))

    result = await fallback.parse(text="message", state=state)

    assert result.resolution_status is NLUResolutionStatus.RESOLVED
    assert result.payload == expected


@pytest.mark.asyncio
async def test_multiple_known_entities_only_use_the_current_intent_payload() -> None:
    fallback, _ = fallback_for(
        structured(
            intent="select_people",
            entities={
                "number_of_people": 3,
                "booking_date": "2026-08-03",
                "duration_minutes": 60,
            },
        )
    )

    result = await fallback.parse(
        text="Mai tôi đi cùng hai người bạn",
        state=BookingState.SELECTING_PEOPLE,
    )

    assert result.payload == {"num_customer": 3}


@pytest.mark.asyncio
async def test_llm_change_output_maps_target_and_primitive_value() -> None:
    fallback, gateway = fallback_for(
        structured(
            intent="change_booking_field",
            entities={"change_target": "people", "number_of_people": 2},
        )
    )

    result = await fallback.parse(
        text="Cho mình đổi sang hai người",
        state=BookingState.AWAITING_CONFIRMATION,
    )

    assert result.intent == "change_info"
    assert result.payload == {"change_target": "people", "num_customer": 2}
    assert gateway.calls == 1


@pytest.mark.asyncio
async def test_llm_change_shop_query_stays_domain_neutral() -> None:
    fallback, _ = fallback_for(
        structured(
            intent="change_booking_field",
            entities={"change_target": "shop"},
            entity_kind="shop",
            entity_query="quận 1",
        )
    )

    result = await fallback.parse(
        text="Đổi sang chi nhánh gần quận 1",
        state=BookingState.AWAITING_CONFIRMATION,
    )

    assert result.resolution_status is NLUResolutionStatus.ENTITY_RESOLUTION_REQUIRED
    assert result.entity_kind is NLUEntityKind.SHOP
    assert result.entity_query == "quận 1"
    assert result.change_target == "shop"
    assert result.payload == {}


@pytest.mark.asyncio
async def test_shop_query_maps_to_entity_resolution_without_domain_object() -> None:
    fallback, _ = fallback_for(
        structured(
            intent="select_shop",
            entity_kind="shop",
            entity_query="quận 1",
        )
    )

    result = await fallback.parse(
        text="Tôi muốn tới chi nhánh gần quận 1",
        state=BookingState.SELECTING_SHOP,
    )

    assert result.resolution_status is NLUResolutionStatus.ENTITY_RESOLUTION_REQUIRED
    assert result.intent is None
    assert result.payload == {}
    assert result.entity_kind is NLUEntityKind.SHOP
    assert result.entity_query == "quận 1"


@pytest.mark.asyncio
async def test_therapist_gender_becomes_an_entity_query() -> None:
    fallback, _ = fallback_for(
        structured(
            intent="select_therapist",
            entities={"therapist_gender": "female"},
        )
    )

    result = await fallback.parse(
        text="Kỹ thuật viên nữ",
        state=BookingState.SELECTING_THERAPIST,
    )

    assert result.resolution_status is NLUResolutionStatus.ENTITY_RESOLUTION_REQUIRED
    assert result.entity_kind is NLUEntityKind.THERAPIST
    assert result.entity_query == "female"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content",
    [
        "not-json",
        "",
        structured(intent="unknown"),
        structured(intent="select_people", confidence=0.69, entities={"number_of_people": 2}),
        structured(intent="confirm"),
        structured(intent="select_people", entities={"number_of_people": "3"}),
        structured(intent="select_people", entities={"shop": {"shop_id": "secret"}}),
        structured(intent="select_people", unexpected=True),
        structured(intent="select_date", entities={"booking_date": "03/08/2026"}),
        structured(intent="select_time", entities={"start_time": "after dinner"}),
    ],
)
async def test_invalid_unsafe_or_state_disallowed_output_is_unresolved(
    content: str,
) -> None:
    fallback, gateway = fallback_for(content)

    result = await fallback.parse(text="ambiguous", state=BookingState.SELECTING_PEOPLE)

    assert result.resolution_status is NLUResolutionStatus.UNRESOLVED
    assert result.intent is None
    assert result.payload == {}
    assert gateway.calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [TimeoutError(), LLMGatewayUnavailableError("unavailable")],
)
async def test_expected_provider_failure_returns_safe_unresolved(
    error: BaseException,
) -> None:
    gateway = FakeLLMGateway(error=error)
    fallback = LLMNLUFallback(llm_gateway=gateway, intent_policy=policy())

    result = await fallback.parse(text="message", state=BookingState.SELECTING_PEOPLE)

    assert result.resolution_status is NLUResolutionStatus.UNRESOLVED
    assert gateway.calls == 1


@pytest.mark.asyncio
async def test_programmer_error_propagates() -> None:
    gateway = FakeLLMGateway(error=RuntimeError("programmer error"))
    fallback = LLMNLUFallback(llm_gateway=gateway, intent_policy=policy())

    with pytest.raises(RuntimeError, match="programmer error"):
        await fallback.parse(text="message", state=BookingState.SELECTING_PEOPLE)


@pytest.mark.asyncio
async def test_cancellation_propagates() -> None:
    gateway = FakeLLMGateway(error=asyncio.CancelledError())
    fallback = LLMNLUFallback(llm_gateway=gateway, intent_policy=policy())

    with pytest.raises(asyncio.CancelledError):
        await fallback.parse(text="message", state=BookingState.SELECTING_PEOPLE)


@pytest.mark.asyncio
async def test_disabled_fallback_does_not_call_gateway() -> None:
    gateway = FakeLLMGateway(LLMResponse(content=structured(intent="start_booking")))
    fallback = LLMNLUFallback(
        llm_gateway=gateway,
        intent_policy=policy(),
        enabled=False,
    )

    result = await fallback.parse(text="message", state=BookingState.IDLE)

    assert result.resolution_status is NLUResolutionStatus.UNRESOLVED
    assert gateway.calls == 0


@pytest.mark.asyncio
async def test_prompt_is_state_aware_short_and_contains_no_context_data() -> None:
    fallback, gateway = fallback_for(
        structured(intent="select_people", entities={"number_of_people": 2})
    )

    await fallback.parse(text="hai người", state=BookingState.SELECTING_PEOPLE)

    assert len(gateway.messages) == 2
    prompt = gateway.messages[0].content
    assert "selecting_people" in prompt
    assert "select_people" in prompt
    assert "JSON only" in prompt
    assert "BookingContext" not in prompt
    assert "API key" not in prompt
    assert "UUID" not in prompt
    assert len(prompt) < 1000
