"""Unit tests for deterministic, state-aware NLU parsing."""

from datetime import date, time
from types import MappingProxyType

import pytest

from app.dialog.flow_loader import FlowDefinition, FlowOnEnter, FlowState, FlowTransition
from app.dialog.nlu import (
    DeterministicNLU,
    NLUEntityKind,
    NLUResolutionStatus,
    NLUResult,
    NLUResultNotDispatchableError,
    NLUSource,
    StateIntentPolicy,
    build_state_intent_policy,
    to_dialog_turn_input,
)
from app.domain.booking_context import BookingContext
from app.domain.booking_state import BookingState

FIXED_TODAY = date(2026, 8, 1)


@pytest.fixture
def nlu() -> DeterministicNLU:
    return DeterministicNLU(
        intent_policy=intent_policy(),
        today_provider=lambda: FIXED_TODAY,
    )


def intent_policy() -> StateIntentPolicy:
    return StateIntentPolicy(
        {
            BookingState.IDLE: frozenset(
                {"greeting", "thanks", "start_booking", "ask_question", "unknown"}
            ),
            BookingState.SELECTING_SHOP: frozenset(
                {"select_store", "ask_question", "cancel_flow", "unknown"}
            ),
            BookingState.SELECTING_DATE: frozenset(
                {"select_date", "ask_question", "cancel_flow", "unknown"}
            ),
            BookingState.SELECTING_PEOPLE: frozenset(
                {"select_people", "deny", "cancel_flow", "unknown"}
            ),
            BookingState.SELECTING_DURATION: frozenset(
                {"select_duration", "deny", "cancel_flow", "unknown"}
            ),
            BookingState.SELECTING_SERVICE: frozenset(
                {
                    "select_course",
                    "select_duration",
                    "list_available_times",
                    "list_therapists",
                    "change_info",
                    "cancel_flow",
                    "unknown",
                }
            ),
            BookingState.SELECTING_TIME: frozenset(
                {"select_time", "deny", "cancel_flow", "unknown"}
            ),
            BookingState.SELECTING_THERAPIST: frozenset(
                {"select_therapist", "deny", "cancel_flow", "unknown"}
            ),
            BookingState.COLLECTING_PHONE: frozenset(
                {"provide_phone", "cancel_flow", "unknown"}
            ),
            BookingState.VERIFYING_PHONE: frozenset(
                {"provide_phone", "confirm", "deny", "cancel_flow", "unknown"}
            ),
            BookingState.AWAITING_CONFIRMATION: frozenset(
                {"confirm", "deny", "change_info", "cancel_flow", "unknown"}
            ),
            BookingState.BOOKING_FAILED: frozenset(
                {"confirm", "deny", "select_time", "unknown"}
            ),
        },
        frozenset(
            {
                BookingState.IDLE,
                BookingState.SELECTING_SHOP,
                BookingState.SELECTING_DATE,
            }
        ),
    )


def test_state_intent_policy_defensively_copies_and_separates_wildcard() -> None:
    source = {BookingState.IDLE: frozenset({"start_booking", "unknown"})}
    policy = StateIntentPolicy(source, frozenset({BookingState.IDLE}))
    source[BookingState.IDLE] = frozenset({"changed"})

    assert policy.allowed_for(BookingState.IDLE) == frozenset(
        {"start_booking", "unknown"}
    )
    assert policy.allowed_for(BookingState.COMPLETED) == frozenset()
    assert policy.is_allowed(BookingState.IDLE, "start_booking")
    assert not policy.is_allowed(BookingState.IDLE, "*")
    assert policy.has_wildcard(BookingState.IDLE)
    with pytest.raises(TypeError):
        policy.allowed_intents[BookingState.IDLE] = frozenset()  # type: ignore[index]


def test_build_policy_extracts_only_intent_availability_from_flow() -> None:
    flow = FlowDefinition(
        version="1",
        name="policy-test",
        description=None,
        initial_state=BookingState.IDLE,
        states={
            BookingState.IDLE: FlowState(
                description="test",
                on_enter=FlowOnEnter("greeting"),
                transitions=(
                    FlowTransition(
                        "start_booking",
                        BookingState.SELECTING_SHOP,
                        actions=("search_shop",),
                    ),
                    FlowTransition("*", BookingState.IDLE),
                ),
            )
        },
    )

    policy = build_state_intent_policy(flow)

    assert policy.allowed_for(BookingState.IDLE) == frozenset({"start_booking"})
    assert policy.has_wildcard(BookingState.IDLE)
    assert not hasattr(policy, "actions")
    assert not hasattr(policy, "target")
    assert not hasattr(policy, "instruction_template")


def test_normalization_handles_case_whitespace_and_safe_punctuation(
    nlu: DeterministicNLU,
) -> None:
    result = nlu.parse(text="  HỦY   ĐẶT   LỊCH!!! ", state=BookingState.SELECTING_DATE)

    assert result.intent == "cancel_flow"
    assert result.confidence == 1.0
    assert result.matched_rule == "cancel_exact"


def test_cancel_and_start_booking_require_named_transition(
    nlu: DeterministicNLU,
) -> None:
    allowed_cancel = nlu.parse(text="hủy", state=BookingState.SELECTING_DATE)
    disallowed_cancel = nlu.parse(text="hủy", state=BookingState.IDLE)
    allowed_start = nlu.parse(text="đặt lịch", state=BookingState.IDLE)
    disallowed_start = nlu.parse(
        text="đặt lịch",
        state=BookingState.SELECTING_DATE,
    )

    assert allowed_cancel.resolution_status is NLUResolutionStatus.RESOLVED
    assert disallowed_cancel.resolution_status is NLUResolutionStatus.UNRESOLVED
    assert disallowed_cancel.intent is None
    assert allowed_start.intent == "start_booking"
    assert disallowed_start.resolution_status is NLUResolutionStatus.UNRESOLVED


def test_question_requires_named_state_transition() -> None:
    policy = StateIntentPolicy(
        {BookingState.IDLE: frozenset({"unknown"})},
        frozenset({BookingState.IDLE}),
    )
    parser = DeterministicNLU(
        intent_policy=policy,
        today_provider=lambda: FIXED_TODAY,
    )

    result = parser.parse(text="Giá bao nhiêu?", state=BookingState.IDLE)

    assert result.intent is None
    assert result.resolution_status is NLUResolutionStatus.UNRESOLVED
    assert result.matched_rule == "faq_explicit"


def test_empty_text_uses_unknown_fallback(nlu: DeterministicNLU) -> None:
    result = nlu.parse(text=" \t\n ", state=BookingState.IDLE)

    assert result.intent == "unknown"
    assert result.payload == {}
    assert result.confidence == 0.0
    assert result.source is NLUSource.FALLBACK
    assert result.resolution_status is NLUResolutionStatus.RESOLVED
    assert result.matched_rule is None


def test_unknown_can_be_returned_as_unresolved_for_llm_fallback() -> None:
    parser = DeterministicNLU(
        intent_policy=intent_policy(),
        today_provider=lambda: FIXED_TODAY,
        unknown_as_unresolved=True,
    )

    result = parser.parse(
        text="Khoang mot tieng",
        state=BookingState.SELECTING_DURATION,
    )

    assert result.intent is None
    assert result.resolution_status is NLUResolutionStatus.UNRESOLVED
    assert result.source is NLUSource.FALLBACK


@pytest.mark.parametrize(
    ("text", "target", "value_key", "expected"),
    [
        ("đổi ngày", "date", None, None),
        ("đổi sang ngày mai", "date", "booking_date", date(2026, 8, 2)),
        ("đổi thành 2 người", "people", "num_customer", 2),
        ("đổi sang 60 phút", "duration", "duration_minutes", 60),
        ("chọn lại cửa hàng", "shop", None, None),
        ("chọn liệu trình khác", "service", None, None),
        ("chọn giờ khác", "time", None, None),
        (
            "không yêu cầu kỹ thuật viên nữa",
            "therapist",
            "therapist_gender",
            "none",
        ),
        ("sửa số điện thoại", "phone", None, None),
    ],
)
def test_change_requests_use_one_general_intent(
    nlu: DeterministicNLU,
    text: str,
    target: str,
    value_key: str | None,
    expected: object,
) -> None:
    result = nlu.parse(text=text, state=BookingState.AWAITING_CONFIRMATION)

    assert result.intent == "change_info"
    assert result.payload["change_target"] == target
    assert set(result.payload) == (
        {"change_target"} if value_key is None else {"change_target", value_key}
    )
    if value_key is not None:
        assert result.payload[value_key] == expected


def test_change_shop_query_requires_atomic_entity_resolution(
    nlu: DeterministicNLU,
) -> None:
    result = nlu.parse(
        text="đổi sang chi nhánh Quận 1",
        state=BookingState.AWAITING_CONFIRMATION,
    )

    assert result.resolution_status is NLUResolutionStatus.ENTITY_RESOLUTION_REQUIRED
    assert result.entity_kind is NLUEntityKind.SHOP
    assert result.entity_query == "quận 1"
    assert result.change_target == "shop"


def test_non_booking_change_is_not_a_change_intent(nlu: DeterministicNLU) -> None:
    result = nlu.parse(
        text="đổi tiền giúp tôi",
        state=BookingState.AWAITING_CONFIRMATION,
    )

    assert result.intent != "change_info"


@pytest.mark.parametrize("phrase", ["đúng", "ĐÚNG RỒI!", "ok", "xác nhận"])
def test_confirm_is_state_aware(
    nlu: DeterministicNLU,
    phrase: str,
) -> None:
    supported = nlu.parse(text=phrase, state=BookingState.VERIFYING_PHONE)
    unsupported = nlu.parse(text=phrase, state=BookingState.SELECTING_PEOPLE)

    assert supported.intent == "confirm"
    assert supported.matched_rule == "confirm_exact"
    assert unsupported.intent is None
    assert unsupported.resolution_status is NLUResolutionStatus.UNRESOLVED


@pytest.mark.parametrize("phrase", ["không", "sai", "nhập lại", "no"])
def test_deny_is_state_aware(nlu: DeterministicNLU, phrase: str) -> None:
    supported = nlu.parse(text=phrase, state=BookingState.VERIFYING_PHONE)
    unsupported = nlu.parse(text=phrase, state=BookingState.SELECTING_SHOP)

    assert supported.intent == "deny"
    assert unsupported.intent is None
    assert unsupported.resolution_status is NLUResolutionStatus.UNRESOLVED


def test_people_entity_phrase_is_not_mistaken_for_confirmation(
    nlu: DeterministicNLU,
) -> None:
    result = nlu.parse(text="đúng 2 người", state=BookingState.SELECTING_PEOPLE)

    assert result.intent == "select_people"
    assert result.payload == {"num_customer": 2}


def test_negative_people_phrase_is_deny_not_entity(nlu: DeterministicNLU) -> None:
    result = nlu.parse(
        text="không phải 2 người",
        state=BookingState.SELECTING_PEOPLE,
    )

    assert result.intent == "deny"


def test_people_correction_uses_last_explicit_value(nlu: DeterministicNLU) -> None:
    result = nlu.parse(
        text="không phải 2 người mà 3 người",
        state=BookingState.SELECTING_PEOPLE,
    )

    assert result.intent == "select_people"
    assert result.payload == {"num_customer": 3}
    assert result.matched_rule == "people_correction"


@pytest.mark.parametrize(
    ("phrase", "expected"),
    [
        ("1", 1),
        ("2 người", 2),
        ("ba người", 3),
        ("một người", 1),
        ("4 người", 4),
    ],
)
def test_people_extraction_preserves_value_for_domain_validation(
    nlu: DeterministicNLU,
    phrase: str,
    expected: int,
) -> None:
    result = nlu.parse(text=phrase, state=BookingState.SELECTING_PEOPLE)

    assert result.intent == "select_people"
    assert result.payload["num_customer"] == expected
    assert result.confidence == 0.95


def test_number_outside_people_state_is_not_people(nlu: DeterministicNLU) -> None:
    assert nlu.parse(text="2", state=BookingState.SELECTING_DATE).intent == "unknown"


@pytest.mark.parametrize(
    ("phrase", "expected"),
    [
        ("30 phút", 30),
        ("45 phút", 45),
        ("60", 60),
        ("1 tiếng", 60),
        ("1 tiếng rưỡi", 90),
        ("2 giờ", 120),
    ],
)
def test_duration_extraction(
    nlu: DeterministicNLU,
    phrase: str,
    expected: int,
) -> None:
    result = nlu.parse(text=phrase, state=BookingState.SELECTING_DURATION)

    assert result.intent == "select_duration"
    assert result.payload == {"duration_minutes": expected}


def test_invalid_or_out_of_state_duration_is_unknown(nlu: DeterministicNLU) -> None:
    assert (
        nlu.parse(text="khoảng một lúc", state=BookingState.SELECTING_DURATION).intent
        == "unknown"
    )
    assert nlu.parse(text="60", state=BookingState.SELECTING_DATE).intent == "unknown"


@pytest.mark.parametrize(
    ("phrase", "expected"),
    [
        ("hôm nay", date(2026, 8, 1)),
        ("ngày mai", date(2026, 8, 2)),
        ("ngày kia", date(2026, 8, 3)),
        ("05/08", date(2026, 8, 5)),
        ("05/08/2027", date(2027, 8, 5)),
        ("2027-08-05", date(2027, 8, 5)),
        ("01/01/2025", date(2025, 1, 1)),
    ],
)
def test_date_extraction_with_injected_today(
    nlu: DeterministicNLU,
    phrase: str,
    expected: date,
) -> None:
    result = nlu.parse(text=phrase, state=BookingState.SELECTING_DATE)

    assert result.intent == "select_date"
    assert result.payload["booking_date"] == expected
    assert isinstance(result.payload["booking_date"], date)


def test_invalid_or_ambiguous_date_is_unknown(nlu: DeterministicNLU) -> None:
    assert nlu.parse(text="31/02/2026", state=BookingState.SELECTING_DATE).intent == "unknown"
    assert (
        nlu.parse(text="thứ bảy tuần sau", state=BookingState.SELECTING_DATE).intent
        == "unknown"
    )


@pytest.mark.parametrize(
    ("phrase", "expected"),
    [
        ("19:00", time(19, 0)),
        ("19h", time(19, 0)),
        ("19h30", time(19, 30)),
        ("7 giờ tối", time(19, 0)),
        ("7h tối", time(19, 0)),
        ("9 giờ sáng", time(9, 0)),
    ],
)
def test_time_extraction(
    nlu: DeterministicNLU,
    phrase: str,
    expected: time,
) -> None:
    result = nlu.parse(text=phrase, state=BookingState.SELECTING_TIME)

    assert result.intent == "select_time"
    assert result.payload["start_time"] == expected
    assert isinstance(result.payload["start_time"], time)


def test_ambiguous_or_out_of_state_time_is_unknown(nlu: DeterministicNLU) -> None:
    assert nlu.parse(text="7 giờ", state=BookingState.SELECTING_TIME).intent == "unknown"
    assert nlu.parse(text="19h", state=BookingState.SELECTING_DATE).intent == "unknown"


def test_time_extraction_recovers_from_booking_failed(
    nlu: DeterministicNLU,
) -> None:
    result = nlu.parse(text="10:00", state=BookingState.BOOKING_FAILED)

    assert result.intent == "select_time"
    assert result.payload["start_time"] == time(10, 0)


@pytest.mark.parametrize(
    ("phrase", "expected"),
    [
        ("0901 234 567", "0901234567"),
        ("0901-234-567", "0901234567"),
        ("+84 901 234 567", "+84901234567"),
    ],
)
def test_phone_candidate_normalization_without_rule_leak(
    nlu: DeterministicNLU,
    phrase: str,
    expected: str,
) -> None:
    result = nlu.parse(text=phrase, state=BookingState.COLLECTING_PHONE)

    assert result.intent == "provide_phone"
    assert result.payload["phone"] == expected
    assert result.matched_rule == "phone_candidate"
    assert expected not in result.matched_rule


def test_invalid_phone_candidate_is_unknown(nlu: DeterministicNLU) -> None:
    result = nlu.parse(text="12345", state=BookingState.COLLECTING_PHONE)

    assert result.intent == "unknown"
    assert result.matched_rule is None


def test_shop_parser_returns_query_without_domain_identity(nlu: DeterministicNLU) -> None:
    result = nlu.parse(
        text="Chi nhánh Quận 1",
        state=BookingState.SELECTING_SHOP,
    )

    assert result.intent is None
    assert result.payload == {}
    assert result.resolution_status is NLUResolutionStatus.ENTITY_RESOLUTION_REQUIRED
    assert result.entity_kind is NLUEntityKind.SHOP
    assert result.entity_query == "quận 1"


@pytest.mark.parametrize(
    ("phrase", "expected_query"),
    [
        ("tôi muốn đặt cửa hàng Komorebi Ba Đình", "komorebi ba đình"),
        ("tôi muốn đặt chi nhánh Komorebi Bình Thạnh", "komorebi bình thạnh"),
        ("cho tôi chi nhánh Ba Đình nhé", "ba đình"),
        ("đặt ở Komorebi Cần Thơ ạ", "komorebi cần thơ"),
    ],
)
def test_shop_parser_extracts_candidate_from_natural_selection_phrase(
    nlu: DeterministicNLU,
    phrase: str,
    expected_query: str,
) -> None:
    result = nlu.parse(text=phrase, state=BookingState.SELECTING_SHOP)

    assert result.intent is None
    assert result.resolution_status is NLUResolutionStatus.ENTITY_RESOLUTION_REQUIRED
    assert result.entity_kind is NLUEntityKind.SHOP
    assert result.entity_query == expected_query


def test_start_booking_phrase_does_not_override_selecting_shop_state(
    nlu: DeterministicNLU,
) -> None:
    result = nlu.parse(
        text="tôi muốn đặt Komorebi Ba Đình4",
        state=BookingState.SELECTING_SHOP,
    )

    assert result.intent is None
    assert result.resolution_status is NLUResolutionStatus.ENTITY_RESOLUTION_REQUIRED
    assert result.entity_query == "komorebi ba đình4"


def test_course_parser_returns_query_and_optional_duration(
    nlu: DeterministicNLU,
) -> None:
    result = nlu.parse(
        text="Massage Thái 60 phút",
        state=BookingState.SELECTING_SERVICE,
    )

    assert result.intent is None
    assert result.payload == {}
    assert result.resolution_status is NLUResolutionStatus.ENTITY_RESOLUTION_REQUIRED
    assert result.entity_kind is NLUEntityKind.COURSE
    assert result.entity_query == "massage thái"
    assert result.has_unconsumed_entities is True


@pytest.mark.parametrize(
    ("phrase", "status", "entity_query"),
    [
        ("không yêu cầu", NLUResolutionStatus.RESOLVED, None),
        (
            "kỹ thuật viên nam",
            NLUResolutionStatus.ENTITY_RESOLUTION_REQUIRED,
            "male",
        ),
        ("nữ", NLUResolutionStatus.ENTITY_RESOLUTION_REQUIRED, "female"),
        ("chọn chị Lan", NLUResolutionStatus.ENTITY_RESOLUTION_REQUIRED, "lan"),
    ],
)
def test_therapist_extraction_does_not_create_domain_identity(
    nlu: DeterministicNLU,
    phrase: str,
    status: NLUResolutionStatus,
    entity_query: str | None,
) -> None:
    result = nlu.parse(text=phrase, state=BookingState.SELECTING_THERAPIST)

    assert result.resolution_status is status
    assert result.payload == {}
    assert result.entity_query == entity_query
    if entity_query is None:
        assert result.intent == "deny"
    else:
        assert result.intent is None
        assert result.entity_kind is NLUEntityKind.THERAPIST


def test_multi_entity_sentence_marks_but_does_not_dispatch_secondary_entities(
    nlu: DeterministicNLU,
) -> None:
    result = nlu.parse(
        text="ngày mai lúc 7 giờ tối cho 2 người",
        state=BookingState.SELECTING_DATE,
    )

    assert result.intent == "select_date"
    assert result.payload == {"booking_date": date(2026, 8, 2)}
    assert result.has_unconsumed_entities is True
    assert "start_time" not in result.payload
    assert "num_customer" not in result.payload


def test_booking_request_and_question_use_real_flow_intents(
    nlu: DeterministicNLU,
) -> None:
    start = nlu.parse(text="Tôi muốn đặt lịch", state=BookingState.IDLE)
    question = nlu.parse(text="Giá bao nhiêu?", state=BookingState.IDLE)

    assert start.intent == "start_booking"
    assert question.intent == "ask_question"
    assert question.payload == {"query": "Giá bao nhiêu?"}


@pytest.mark.parametrize(
    "text",
    [
        "Cửa hàng mở cửa lúc mấy giờ?",
        "Cửa hàng đóng cửa lúc mấy giờ?",
        "Massage Thái giá bao nhiêu?",
        "Có chỗ đậu xe không?",
        "Có nhận khách mang thai không?",
        "Có dịch vụ cho phụ nữ mang thai không?",
        "Dịch vụ có an toàn cho người mang thai không?",
        "Chính sách cho bà bầu như thế nào?",
        "Có lưu ý gì trong thai kỳ?",
        "Chính sách hủy lịch như thế nào?",
        "Tôi cần đến trước bao nhiêu phút?",
    ],
)
def test_explicit_faq_patterns_preserve_original_query(
    nlu: DeterministicNLU,
    text: str,
) -> None:
    result = nlu.parse(text=text, state=BookingState.IDLE)

    assert result.intent == "ask_question"
    assert result.payload == {"query": text}
    assert result.matched_rule == "faq_explicit"


@pytest.mark.parametrize(
    ("text", "state"),
    [
        ("Tôi muốn đặt lúc 19 giờ", BookingState.SELECTING_TIME),
        ("Còn khung giờ nào?", BookingState.SELECTING_TIME),
        ("Chọn giờ nào được?", BookingState.SELECTING_TIME),
        ("Đổi sang 20 giờ", BookingState.AWAITING_CONFIRMATION),
        ("Đặt 2 người", BookingState.SELECTING_PEOPLE),
    ],
)
def test_booking_and_change_phrases_are_not_misclassified_as_faq(
    nlu: DeterministicNLU,
    text: str,
    state: BookingState,
) -> None:
    result = nlu.parse(text=text, state=state)

    assert result.intent != "ask_question"


def test_unknown_question_is_unresolved_in_production_fallback_mode() -> None:
    parser = DeterministicNLU(
        intent_policy=intent_policy(),
        today_provider=lambda: FIXED_TODAY,
        unknown_as_unresolved=True,
    )

    result = parser.parse(text="Bạn nghĩ sao về điều này?", state=BookingState.IDLE)

    assert result.resolution_status is NLUResolutionStatus.UNRESOLVED
    assert result.matched_rule == "question_unresolved"


def test_ambiguous_sentence_uses_unknown(
    nlu: DeterministicNLU,
) -> None:
    result = nlu.parse(text="cuối tuần sau", state=BookingState.IDLE)

    assert result == NLUResult(
        "unknown",
        {},
        0.0,
        NLUSource.FALLBACK,
        NLUResolutionStatus.RESOLVED,
    )


@pytest.mark.parametrize(
    ("phrase", "intent"),
    [("xin chào", "greeting"), ("cảm ơn", "thanks")],
)
def test_social_intents_are_catalog_resolved(
    nlu: DeterministicNLU,
    phrase: str,
    intent: str,
) -> None:
    result = nlu.parse(text=phrase, state=BookingState.IDLE)

    assert result.intent == intent
    assert result.source is NLUSource.DETERMINISTIC
    assert result.resolution_status is NLUResolutionStatus.RESOLVED


def test_wildcard_without_named_unknown_stays_unresolved() -> None:
    policy = StateIntentPolicy(
        {BookingState.IDLE: frozenset()},
        frozenset({BookingState.IDLE}),
    )
    parser = DeterministicNLU(
        intent_policy=policy,
        today_provider=lambda: FIXED_TODAY,
    )

    result = parser.parse(text="không hiểu", state=BookingState.IDLE)

    assert policy.has_wildcard(BookingState.IDLE)
    assert result.intent is None
    assert result.resolution_status is NLUResolutionStatus.UNRESOLVED
    assert result.is_dispatchable() is False


def test_mapper_preserves_typed_payload_and_request_metadata(
    nlu: DeterministicNLU,
) -> None:
    parsed = nlu.parse(text="ngày mai", state=BookingState.SELECTING_DATE)

    turn = to_dialog_turn_input(
        parsed,
        state=BookingState.SELECTING_DATE,
        intent_policy=intent_policy(),
        idempotency_key="stable-key",
        raw_message="ngày mai",
    )

    assert turn.intent == parsed.intent
    assert turn.payload == parsed.payload
    assert isinstance(turn.payload["booking_date"], date)
    assert turn.idempotency_key == "stable-key"
    assert turn.raw_message == "ngày mai"
    assert parsed.payload == {"booking_date": date(2026, 8, 2)}


@pytest.mark.parametrize(
    "result",
    [
        NLUResult(
            None,
            {},
            0.0,
            NLUSource.FALLBACK,
            NLUResolutionStatus.UNRESOLVED,
        ),
        NLUResult(
            None,
            {},
            0.8,
            NLUSource.DETERMINISTIC,
            NLUResolutionStatus.ENTITY_RESOLUTION_REQUIRED,
            entity_query="quận 1",
            entity_kind=NLUEntityKind.SHOP,
        ),
    ],
)
def test_mapper_rejects_non_dispatchable_results(result: NLUResult) -> None:
    with pytest.raises(NLUResultNotDispatchableError):
        to_dialog_turn_input(
            result,
            state=BookingState.SELECTING_SHOP,
            intent_policy=intent_policy(),
        )


def test_mapper_rejects_disallowed_intent_and_extra_payload() -> None:
    disallowed = NLUResult(
        "confirm",
        {},
        1.0,
        NLUSource.DETERMINISTIC,
        NLUResolutionStatus.RESOLVED,
    )
    extra_payload = NLUResult(
        "select_date",
        {"booking_date": date(2026, 8, 2), "start_time": time(19, 0)},
        0.95,
        NLUSource.DETERMINISTIC,
        NLUResolutionStatus.RESOLVED,
    )
    unresolved_selection = NLUResult(
        "select_store",
        {},
        0.8,
        NLUSource.DETERMINISTIC,
        NLUResolutionStatus.RESOLVED,
    )

    with pytest.raises(NLUResultNotDispatchableError):
        to_dialog_turn_input(
            disallowed,
            state=BookingState.SELECTING_DATE,
            intent_policy=intent_policy(),
        )
    with pytest.raises(NLUResultNotDispatchableError):
        to_dialog_turn_input(
            extra_payload,
            state=BookingState.SELECTING_DATE,
            intent_policy=intent_policy(),
        )
    with pytest.raises(NLUResultNotDispatchableError):
        to_dialog_turn_input(
            unresolved_selection,
            state=BookingState.SELECTING_SHOP,
            intent_policy=intent_policy(),
        )


def test_mapper_error_does_not_include_phone_or_raw_message() -> None:
    phone = "0901234567"
    invalid = NLUResult(
        "provide_phone",
        {"phone": phone, "unexpected": True},
        0.95,
        NLUSource.DETERMINISTIC,
        NLUResolutionStatus.RESOLVED,
    )

    with pytest.raises(NLUResultNotDispatchableError) as captured:
        to_dialog_turn_input(
            invalid,
            state=BookingState.COLLECTING_PHONE,
            intent_policy=intent_policy(),
            raw_message=phone,
        )

    assert phone not in str(captured.value)


def test_result_payload_is_deeply_immutable() -> None:
    source_payload: dict[str, object] = {"nested": {"values": [1, 2]}}
    result = NLUResult(
        "unknown",
        source_payload,
        0.0,
        NLUSource.FALLBACK,
        NLUResolutionStatus.RESOLVED,
    )
    source_payload["nested"] = "changed"

    assert isinstance(result.payload, MappingProxyType)
    assert result.payload["nested"] == {"values": (1, 2)}
    with pytest.raises(TypeError):
        result.payload["new"] = 1  # type: ignore[index]


def test_parser_does_not_mutate_context_or_input(nlu: DeterministicNLU) -> None:
    context = BookingContext("conversation-1", state=BookingState.SELECTING_PEOPLE)
    text = " 2 người "

    nlu.parse(text=text, state=context.state)

    assert text == " 2 người "
    assert context == BookingContext(
        "conversation-1",
        state=BookingState.SELECTING_PEOPLE,
    )


@pytest.mark.parametrize(
    ("text", "intent"),
    [
        ("tại sao", "ask_why"),
        ("cho tôi xem lịch trống", "list_available_times"),
        ("hôm đó có therapist nào", "list_therapists"),
        ("xin chào", "greeting"),
    ],
)
def test_global_intents_precede_service_entity_fallback(
    nlu: DeterministicNLU,
    text: str,
    intent: str,
) -> None:
    result = nlu.parse(text=text, state=BookingState.SELECTING_SERVICE)

    assert result.intent == intent
    assert result.entity_kind is None


@pytest.mark.parametrize("text", ["60", "60 phút", "đổi sang 90 phút"])
def test_duration_correction_is_not_a_service_query(
    nlu: DeterministicNLU,
    text: str,
) -> None:
    result = nlu.parse(text=text, state=BookingState.SELECTING_SERVICE)

    assert result.intent in {"select_duration", "change_info"}
    assert result.entity_kind is None


def test_change_shop_without_new_name_is_not_an_entity_search(
    nlu: DeterministicNLU,
) -> None:
    result = nlu.parse(
        text="tôi muốn đổi cửa hàng",
        state=BookingState.SELECTING_SERVICE,
    )

    assert result.intent == "change_info"
    assert result.payload == {"change_target": "shop"}
    assert result.entity_kind is None
