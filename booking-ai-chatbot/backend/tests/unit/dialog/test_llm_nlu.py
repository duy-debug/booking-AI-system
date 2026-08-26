"""Unit tests for structured, state-aware LLM NLU fallback."""

import asyncio
import json
from datetime import date, datetime, time, timezone

import pytest

from app.dialog.nlu import (
    LLMNLU,
    NLUEntityKind,
    NLUResolutionStatus,
    NLUSource,
    StateIntentPolicy,
)
from app.domain.booking_state import BookingState
from app.infrastructure.gemini_client import (
    LLMGatewayUnavailableError,
    LLMMessage,
    LLMResponse,
)


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
        self.tools: list[dict[str, object]] | None = None

    async def generate(
        self,
        messages: list[LLMMessage],
        *,
        tools: list[dict[str, object]] | None = None,
    ) -> LLMResponse:
        self.calls += 1
        self.messages = messages
        self.tools = tools
        if self.error is not None:
            raise self.error
        return self.response


def policy() -> StateIntentPolicy:
    allowed = {
        BookingState.IDLE: frozenset({"start_booking", "cancel_existing_booking", "unknown"}),
        BookingState.COLLECTING_CANCEL_BOOKING_IDENTITY: frozenset(
            {"start_booking", "cancel_existing_booking", "unknown"}
        ),
        BookingState.AWAITING_CANCEL_CONFIRMATION: frozenset(
            {"confirm", "deny", "cancel_flow", "unknown"}
        ),
        BookingState.SELECTING_SHOP: frozenset({"select_store", "unknown"}),
        BookingState.SELECTING_DATE: frozenset({"select_date", "unknown"}),
        BookingState.SELECTING_PEOPLE: frozenset({"select_people", "unknown"}),
        BookingState.SELECTING_DURATION: frozenset({"select_duration", "unknown"}),
        BookingState.SELECTING_SERVICE: frozenset({"select_course", "unknown"}),
        BookingState.SELECTING_TIME: frozenset({"select_time", "unknown"}),
        BookingState.SELECTING_THERAPIST: frozenset({"select_therapist", "deny", "unknown"}),
        BookingState.COLLECTING_PHONE: frozenset({"provide_phone", "unknown"}),
        BookingState.COLLECTING_NAME: frozenset({"provide_name", "unknown"}),
        BookingState.AWAITING_CONFIRMATION: frozenset(
            {"confirm", "deny", "change_info", "unknown"}
        ),
    }
    return StateIntentPolicy(
        {state: intents | {"ask_question"} for state, intents in allowed.items()},
        frozenset(),
    )


def draft_change_policy() -> StateIntentPolicy:
    allowed = {
        BookingState.SELECTING_SHOP: frozenset({"change_info", "unknown"}),
        BookingState.SELECTING_DURATION: frozenset({"change_info", "unknown"}),
        BookingState.SELECTING_SERVICE: frozenset({"change_info", "unknown"}),
        BookingState.SELECTING_TIME: frozenset({"change_info", "select_time", "unknown"}),
        BookingState.SELECTING_THERAPIST: frozenset({"change_info", "unknown"}),
        BookingState.COLLECTING_PHONE: frozenset({"change_info", "provide_phone", "unknown"}),
        BookingState.AWAITING_CONFIRMATION: frozenset(
            {"change_info", "confirm", "deny", "unknown"}
        ),
    }
    return StateIntentPolicy(
        {state: intents | {"ask_question"} for state, intents in allowed.items()},
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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("intent", "entities", "expected_payload"),
    [
        ("list_shops", {}, {}),
        ("list_services", {}, {}),
        ("list_addons", {}, {}),
        ("list_available_times", {}, {}),
        ("list_therapists", {}, {}),
        ("search_shops", {"query": "Huế"}, {"location_query": "Huế"}),
    ],
)
async def test_llm_supports_discovery_intents_without_inventing_entities(
    intent: str,
    entities: dict[str, object],
    expected_payload: dict[str, object],
) -> None:
    gateway = FakeLLMGateway(LLMResponse(content=structured(intent=intent, entities=entities)))
    fallback = LLMNLU(
        llm_gateway=gateway,
        intent_policy=StateIntentPolicy(
            {BookingState.IDLE: frozenset({intent})},
            frozenset(),
        ),
    )

    result = await fallback.parse(text="discovery request", state=BookingState.IDLE)

    assert result.intent == intent
    assert result.payload == expected_payload
    assert result.resolution_status is NLUResolutionStatus.RESOLVED


@pytest.mark.asyncio
@pytest.mark.parametrize("intent", ["greeting", "thanks", "ask_why", "repeat_last_question"])
async def test_global_intents_accept_empty_entities(intent: str) -> None:
    gateway = FakeLLMGateway(LLMResponse(content=structured(intent=intent, entities={})))
    fallback = LLMNLU(
        llm_gateway=gateway,
        intent_policy=StateIntentPolicy(
            {BookingState.IDLE: frozenset({intent})},
            frozenset(),
        ),
    )

    result = await fallback.parse(text="social message", state=BookingState.IDLE)

    assert result.intent == intent
    assert result.payload == {}
    assert result.resolution_status is NLUResolutionStatus.RESOLVED


def fallback_for(
    content: str, *, min_confidence: float = 0.7
) -> tuple[
    LLMNLU,
    FakeLLMGateway,
]:
    gateway = FakeLLMGateway(LLMResponse(content=content))
    return (
        LLMNLU(
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
    assert result.source is NLUSource.LLM
    assert result.confidence == 0.9
    assert gateway.calls == 1
    assert gateway.tools is not None
    tool_function = gateway.tools[0]["function"]
    assert isinstance(tool_function, dict)
    assert tool_function["name"] == "extract_intent_candidates"


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
        (
            BookingState.COLLECTING_NAME,
            "provide_name",
            {"customer_name": "Nguyễn An"},
            {"name": "Nguyễn An"},
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
    assert result.merged_entities == {
        "number_of_people": 3,
        "booking_date": date(2026, 8, 3),
        "duration_minutes": 60,
    }


@pytest.mark.asyncio
async def test_start_booking_preserves_all_supported_secondary_booking_entities() -> None:
    fallback, _ = fallback_for(
        structured(
            intent="start_booking",
            entities={
                "shop_name": "Komorebi Bình Thạnh",
                "booking_date": "2026-08-07",
                "number_of_people": 1,
                "duration_minutes": 60,
                "main_course_name": "Massage đá nóng 60 phút",
                "addon_name": "Ngâm chân thảo dược",
                "skip_addon": False,
                "start_time": "19:00",
                "therapist_name": "An",
                "therapist_gender": "female",
                "phone": "0901234567",
                "customer_name": "Nguyễn Bình",
            },
        )
    )

    result = await fallback.parse(text="booking đầy đủ", state=BookingState.IDLE)

    assert result.intent == "start_booking"
    assert result.merged_entities == {
        "shop_name": "Komorebi Bình Thạnh",
        "booking_date": date(2026, 8, 7),
        "number_of_people": 1,
        "duration_minutes": 60,
        "main_course_name": "Massage đá nóng 60 phút",
        "addon_name": "Ngâm chân thảo dược",
        "skip_addon": False,
        "start_time": time(19, 0),
        "therapist_name": "An",
        "therapist_gender": "female",
        "phone": "0901234567",
        "customer_name": "Nguyễn Bình",
    }


@pytest.mark.asyncio
async def test_start_booking_ignores_empty_entity_resolver_noise() -> None:
    fallback, _ = fallback_for(
        structured(
            intent="start_booking",
            confidence=1.0,
            entities={"booking_date": "2026-08-25"},
            entity_kind="shop",
            entity_query=None,
        )
    )

    result = await fallback.parse(
        text="xin chào tôi muốn đặt booking ngày mai",
        state=BookingState.IDLE,
    )

    assert result.intent == "start_booking"
    assert result.resolution_status is NLUResolutionStatus.RESOLVED
    assert result.entity_kind is None
    assert result.entity_query is None
    assert result.merged_entities == {"booking_date": date(2026, 8, 25)}


@pytest.mark.asyncio
async def test_cancel_booking_ignores_empty_entity_resolver_noise() -> None:
    fallback, _ = fallback_for(
        structured(
            intent="cancel_existing_booking",
            confidence=1.0,
            entities={
                "phone": "0320000031",
                "booking_reference": "89efd734-832a-45e3-94d0-c27386b11627",
            },
            entity_kind="shop",
            entity_query=None,
        )
    )

    result = await fallback.parse(
        text="89efd734-832a-45e3-94d0-c27386b11627 và 0320000031",
        state=BookingState.COLLECTING_CANCEL_BOOKING_IDENTITY,
    )

    assert result.intent == "cancel_existing_booking"
    assert result.resolution_status is NLUResolutionStatus.RESOLVED
    assert result.entity_kind is None
    assert result.entity_query is None
    assert result.payload == {
        "phone": "0320000031",
        "booking_reference": "89efd734-832a-45e3-94d0-c27386b11627",
    }


@pytest.mark.asyncio
async def test_state_prioritization_preserves_secondary_candidate_entities() -> None:
    gateway = FakeLLMGateway(
        LLMResponse(
            content=json.dumps(
                {
                    "candidates": [
                        {
                            "intent": "start_booking",
                            "confidence": 0.91,
                            "entities": {
                                "shop_name": "Komorebi Ba Đình",
                                "booking_date": "2026-08-07",
                                "start_time": "10:00",
                            },
                            "entity_kind": None,
                            "entity_query": None,
                        },
                        {
                            "intent": "select_time",
                            "confidence": 0.99,
                            "entities": {"start_time": "10:00"},
                            "entity_kind": None,
                            "entity_query": None,
                        },
                    ]
                }
            )
        )
    )
    nlu = LLMNLU(llm_gateway=gateway, intent_policy=policy())

    result = await nlu.parse(
        text="Đặt Komorebi Ba Đình ngày mai lúc 10 giờ",
        state=BookingState.IDLE,
    )

    assert result.intent == "start_booking"
    assert result.merged_entities == {
        "shop_name": "Komorebi Ba Đình",
        "booking_date": date(2026, 8, 7),
        "start_time": time(10, 0),
    }
    assert result.has_unconsumed_entities is True


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
@pytest.mark.parametrize(
    "state",
    [
        BookingState.SELECTING_SHOP,
        BookingState.SELECTING_DURATION,
        BookingState.SELECTING_SERVICE,
        BookingState.SELECTING_TIME,
        BookingState.SELECTING_THERAPIST,
        BookingState.COLLECTING_PHONE,
        BookingState.AWAITING_CONFIRMATION,
    ],
)
async def test_llm_change_info_is_supported_across_draft_states_when_policy_allows_it(
    state: BookingState,
) -> None:
    gateway = FakeLLMGateway(
        LLMResponse(
            content=structured(
                intent="change_booking_field",
                entities={"change_target": "duration"},
            )
        )
    )
    fallback = LLMNLU(llm_gateway=gateway, intent_policy=draft_change_policy())

    result = await fallback.parse(
        text="mình muốn chỉnh lại độ dài lịch hẹn",
        state=state,
    )

    assert result.intent == "change_info"
    assert result.payload == {"change_target": "duration"}
    assert result.resolution_status is NLUResolutionStatus.RESOLVED
    assert gateway.calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "raw_entities", "expected_payload"),
    [
        (
            "mình muốn điều chỉnh độ dài buổi hẹn",
            {"change_target": "duration"},
            {"change_target": "duration"},
        ),
        (
            "dời khung giờ giúp mình nhé",
            {"change_target": "time"},
            {"change_target": "time"},
        ),
        (
            "cập nhật lại số liên hệ cho mình",
            {"change_target": "phone"},
            {"change_target": "phone"},
        ),
    ],
)
async def test_llm_change_output_maps_semantic_targets_without_backend_inference(
    text: str,
    raw_entities: dict[str, object],
    expected_payload: dict[str, object],
) -> None:
    fallback, gateway = fallback_for(
        structured(
            intent="change_booking_field",
            entities=raw_entities,
        )
    )

    result = await fallback.parse(
        text=text,
        state=BookingState.AWAITING_CONFIRMATION,
    )

    assert result.intent == "change_info"
    assert result.payload == expected_payload
    assert gateway.calls == 1
    prompt = gateway.messages[0].content
    assert "Với change_info, suy ra change_target từ khái niệm ngữ nghĩa" in prompt
    assert "Không được đoán target." in prompt
    assert text not in prompt


@pytest.mark.asyncio
async def test_llm_change_output_allows_generic_change_without_target() -> None:
    fallback, gateway = fallback_for(
        structured(
            intent="change_booking_field",
            entities={"change_target": None},
        )
    )

    text = "mình cần chỉnh lại vài thông tin của lịch hẹn này"
    result = await fallback.parse(text=text, state=BookingState.AWAITING_CONFIRMATION)

    assert result.intent == "change_info"
    assert result.payload == {}
    assert result.resolution_status is NLUResolutionStatus.RESOLVED
    assert gateway.calls == 1
    assert text not in gateway.messages[0].content


@pytest.mark.asyncio
async def test_existing_booking_change_from_idle_is_not_collapsed_into_change_info() -> None:
    fallback, gateway = fallback_for(
        structured(
            intent="change_booking_field",
            entities={"change_target": None},
        )
    )

    result = await fallback.parse(
        text="mình muốn dời lịch đã tạo sang ngày khác",
        state=BookingState.IDLE,
    )

    assert result.resolution_status is NLUResolutionStatus.UNRESOLVED
    assert result.intent is None
    assert result.payload == {}
    assert gateway.calls == 1
    assert (
        "Sửa/dời/hủy booking đã tạo không được gộp vào change_info"
        in gateway.messages[0].content
    )


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
async def test_llm_faq_output_preserves_query_without_generating_answer() -> None:
    fallback, gateway = fallback_for(
        structured(
            intent="ask_question",
            entities={"query": "Có dịch vụ cho khách mang thai không?"},
        )
    )

    result = await fallback.parse(
        text="Mình đang có em bé thì dùng dịch vụ nào được?",
        state=BookingState.IDLE,
    )

    assert result.intent == "ask_question"
    assert result.payload == {"query": "Có dịch vụ cho khách mang thai không?"}
    assert gateway.calls == 1


@pytest.mark.asyncio
async def test_llm_faq_output_accepts_entity_query_as_rag_query() -> None:
    gateway = FakeLLMGateway(
        LLMResponse(
            content=json.dumps(
                {
                    "candidates": [
                        {
                            "intent": "ask_question",
                            "confidence": 1,
                            "entities": {},
                            "entity_kind": None,
                            "entity_query": "Người phụ nữ mang thai có thể massage không?",
                        }
                    ]
                }
            )
        )
    )
    fallback = LLMNLU(
        llm_gateway=gateway,
        intent_policy=policy(),
    )

    result = await fallback.parse(
        text="Người phụ nữ mang thai có thể massage không?",
        state=BookingState.IDLE,
    )

    assert result.intent == "ask_question"
    assert result.payload == {
        "query": "Người phụ nữ mang thai có thể massage không?",
    }
    assert result.confidence == 1.0


@pytest.mark.asyncio
async def test_shop_query_maps_to_entity_resolution_without_domain_object() -> None:
    fallback, _ = fallback_for(
        structured(
            intent="select_store",
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
async def test_shop_name_entity_bridges_to_entity_resolution_request() -> None:
    fallback, _ = fallback_for(
        structured(
            intent="select_store",
            entities={"shop_name": "Komorebi Tân Bình"},
        )
    )

    result = await fallback.parse(
        text="cửa hàng này Komorebi Tân Bình",
        state=BookingState.SELECTING_SHOP,
    )

    assert result.resolution_status is NLUResolutionStatus.ENTITY_RESOLUTION_REQUIRED
    assert result.intent is None
    assert result.payload == {}
    assert result.entity_kind is NLUEntityKind.SHOP
    assert result.entity_query == "Komorebi Tân Bình"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("entities", "expected_query"),
    [
        ({"service_name": "Massage thư giãn toàn thân"}, "Massage thư giãn toàn thân"),
        ({"main_course_name": "Massage đá nóng 60 phút"}, "Massage đá nóng 60 phút"),
        ({"addon_name": "Ngâm chân thảo dược"}, "Ngâm chân thảo dược"),
    ],
)
async def test_course_entities_bridge_to_entity_resolution_request(
    entities: dict[str, object],
    expected_query: str,
) -> None:
    fallback, _ = fallback_for(structured(intent="select_course", entities=entities))

    result = await fallback.parse(
        text="tôi chọn liệu trình này",
        state=BookingState.SELECTING_SERVICE,
    )

    assert result.resolution_status is NLUResolutionStatus.ENTITY_RESOLUTION_REQUIRED
    assert result.intent is None
    assert result.payload == {}
    assert result.entity_kind is NLUEntityKind.COURSE
    assert result.entity_query == expected_query


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
async def test_therapist_name_becomes_entity_resolution_query() -> None:
    fallback, _ = fallback_for(
        structured(
            intent="select_therapist",
            entities={"therapist_name": "Quách Đình Khôi"},
        )
    )

    result = await fallback.parse(
        text="Quách Đình Khôi",
        state=BookingState.SELECTING_THERAPIST,
    )

    assert result.resolution_status is NLUResolutionStatus.ENTITY_RESOLUTION_REQUIRED
    assert result.entity_kind is NLUEntityKind.THERAPIST
    assert result.entity_query == "Quách Đình Khôi"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content", "expected_query"),
    [
        (
            json.dumps(
                {
                    "candidates": [
                        {
                            "intent": "select_therapist",
                            "confidence": 0.9,
                            "entities": {"therapist_gender": "Nam"},
                            "entity_kind": None,
                            "entity_query": None,
                        }
                    ]
                }
            ),
            "male",
        ),
        (
            json.dumps(
                {
                    "candidates": [
                        {
                            "intent": "select_therapist",
                            "confidence": 0.9,
                            "entities": {"therapist_gender": "Nữ"},
                            "entity_kind": None,
                            "entity_query": None,
                        }
                    ]
                }
            ),
            "female",
        ),
        (
            json.dumps(
                {
                    "candidates": [
                        {
                            "intent": "select_therapist",
                            "confidence": 0.9,
                            "entities": {"therapist_gender": "Không yêu cầu"},
                            "entity_kind": None,
                            "entity_query": None,
                        }
                    ]
                }
            ),
            "none",
        ),
    ],
)
async def test_vietnamese_therapist_gender_values_are_canonicalized(
    content: str,
    expected_query: str,
) -> None:
    fallback, _ = fallback_for(content)

    result = await fallback.parse(
        text="therapist preference",
        state=BookingState.SELECTING_THERAPIST,
    )

    assert result.resolution_status is NLUResolutionStatus.ENTITY_RESOLUTION_REQUIRED
    assert result.entity_kind is NLUEntityKind.THERAPIST
    assert result.entity_query == expected_query


@pytest.mark.asyncio
async def test_therapist_none_becomes_entity_query() -> None:
    fallback, _ = fallback_for(
        structured(
            intent="select_therapist",
            entities={"therapist_gender": "none"},
        )
    )

    result = await fallback.parse(
        text="Không yêu cầu",
        state=BookingState.SELECTING_THERAPIST,
    )

    assert result.resolution_status is NLUResolutionStatus.ENTITY_RESOLUTION_REQUIRED
    assert result.entity_kind is NLUEntityKind.THERAPIST
    assert result.entity_query == "none"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("raw_time", "expected"),
    [
        ("8:00", time(8, 0)),
        ("08:00", time(8, 0)),
        ("9:30", time(9, 30)),
        ("09:30", time(9, 30)),
        ("10:00", time(10, 0)),
        ("19:00", time(19, 0)),
    ],
)
async def test_select_time_accepts_single_or_double_digit_hour_formats(
    raw_time: str,
    expected: time,
) -> None:
    fallback, gateway = fallback_for(
        structured(intent="select_time", entities={"start_time": raw_time})
    )

    result = await fallback.parse(text=f"Tôi muốn {raw_time}", state=BookingState.SELECTING_TIME)

    assert result.intent == "select_time"
    assert result.payload == {"start_time": expected}
    assert result.resolution_status is NLUResolutionStatus.RESOLVED
    assert gateway.calls == 1


@pytest.mark.asyncio
async def test_select_time_prompt_uses_semantic_guidance_instead_of_exact_utterance_mapping(
) -> None:
    fallback, gateway = fallback_for(
        structured(intent="select_time", entities={"start_time": "10:00"})
    )

    result = await fallback.parse(text="vậy tôi chọn 10h", state=BookingState.SELECTING_TIME)

    assert result.intent == "select_time"
    assert result.payload == {"start_time": time(10, 0)}
    assert gateway.calls == 1
    prompt = gateway.messages[0].content
    assert "Hãy xem trạng thái hiện tại chỉ như ngữ cảnh hội thoại" in prompt
    assert "Khi người dùng nói giờ bắt đầu cụ thể" in prompt
    assert "Hiểu giờ tự nhiên/viết tắt theo ngữ cảnh" in prompt
    assert "In selecting_time" not in prompt
    assert "In awaiting_confirmation" not in prompt


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "llm_time", "expected"),
    [
        ("chốt cho mình khung chín rưỡi sáng", "09:30", time(9, 30)),
        ("mình lấy lịch tầm bảy giờ tối nhé", "19:00", time(19, 0)),
    ],
)
async def test_select_time_semantic_paraphrases_do_not_need_verbatim_prompt_examples(
    text: str,
    llm_time: str,
    expected: time,
) -> None:
    fallback, gateway = fallback_for(
        structured(intent="select_time", entities={"start_time": llm_time})
    )

    result = await fallback.parse(text=text, state=BookingState.SELECTING_TIME)

    assert result.intent == "select_time"
    assert result.payload == {"start_time": expected}
    assert result.resolution_status is NLUResolutionStatus.RESOLVED
    assert gateway.calls == 1
    assert text not in gateway.messages[0].content


@pytest.mark.asyncio
async def test_selecting_time_state_does_not_force_select_time_when_message_means_change_info(
) -> None:
    gateway = FakeLLMGateway(
        LLMResponse(
            content=structured(
                intent="change_booking_field",
                entities={"change_target": "duration"},
            )
        )
    )
    fallback = LLMNLU(llm_gateway=gateway, intent_policy=draft_change_policy())

    result = await fallback.parse(
        text="mình muốn chỉnh lại độ dài lịch hẹn",
        state=BookingState.SELECTING_TIME,
    )

    assert result.intent == "change_info"
    assert result.payload == {"change_target": "duration"}
    assert result.resolution_status is NLUResolutionStatus.RESOLVED


@pytest.mark.asyncio
async def test_selecting_time_state_allows_unrelated_intent_when_semantics_match() -> None:
    gateway = FakeLLMGateway(
        LLMResponse(
            content=structured(
                intent="ask_question",
                entities={"query": "Chi nhánh này có chỗ gửi xe không?"},
            )
        )
    )
    fallback = LLMNLU(llm_gateway=gateway, intent_policy=draft_change_policy())

    result = await fallback.parse(
        text="chi nhánh này có chỗ gửi xe không",
        state=BookingState.SELECTING_TIME,
    )

    assert result.intent == "ask_question"
    assert result.payload == {"query": "Chi nhánh này có chỗ gửi xe không?"}
    assert result.resolution_status is NLUResolutionStatus.RESOLVED


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
        structured(intent="select_time", entities={"start_time": "25:00"}),
        structured(intent="select_time", entities={"start_time": "8:99"}),
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
    fallback = LLMNLU(llm_gateway=gateway, intent_policy=policy())

    result = await fallback.parse(text="message", state=BookingState.SELECTING_PEOPLE)

    assert result.resolution_status is NLUResolutionStatus.UNRESOLVED
    assert gateway.calls == 1


@pytest.mark.asyncio
async def test_programmer_error_propagates() -> None:
    gateway = FakeLLMGateway(error=RuntimeError("programmer error"))
    fallback = LLMNLU(llm_gateway=gateway, intent_policy=policy())

    with pytest.raises(RuntimeError, match="programmer error"):
        await fallback.parse(text="message", state=BookingState.SELECTING_PEOPLE)


@pytest.mark.asyncio
async def test_cancellation_propagates() -> None:
    gateway = FakeLLMGateway(error=asyncio.CancelledError())
    fallback = LLMNLU(llm_gateway=gateway, intent_policy=policy())

    with pytest.raises(asyncio.CancelledError):
        await fallback.parse(text="message", state=BookingState.SELECTING_PEOPLE)


@pytest.mark.asyncio
async def test_llm_nlu_always_calls_gateway() -> None:
    gateway = FakeLLMGateway(LLMResponse(content=structured(intent="start_booking")))
    fallback = LLMNLU(
        llm_gateway=gateway,
        intent_policy=policy(),
    )

    result = await fallback.parse(text="message", state=BookingState.IDLE)

    assert result.resolution_status is NLUResolutionStatus.RESOLVED
    assert gateway.calls == 1


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
    assert "Chỉ trả về JSON" in prompt
    assert "BookingContext" not in prompt
    assert "API key" not in prompt
    assert "UUID" not in prompt
    assert "Asia/Ho_Chi_Minh" in prompt
    assert "Ngôn ngữ: vi-VN" in prompt
    assert len(prompt) < 2350


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("phrase", "resolved_date"),
    [
        ("hôm nay", "2026-08-06"),
        ("ngày mai", "2026-08-07"),
        ("ngày kia", "2026-08-08"),
    ],
)
async def test_relative_date_prompt_is_grounded_in_fixed_business_date(
    phrase: str,
    resolved_date: str,
) -> None:
    gateway = FakeLLMGateway(
        LLMResponse(
            content=structured(
                intent="select_date",
                entities={"booking_date": resolved_date},
            )
        )
    )
    nlu = LLMNLU(
        llm_gateway=gateway,
        intent_policy=policy(),
        now_provider=lambda: datetime(2026, 8, 5, 17, 0, tzinfo=timezone.utc),
    )

    result = await nlu.parse(text=phrase, state=BookingState.SELECTING_DATE)

    assert result.payload == {"booking_date": date.fromisoformat(resolved_date)}
    assert "Ngày nghiệp vụ hiện tại: 2026-08-06" in gateway.messages[0].content
