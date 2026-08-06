"""Tests for the data-driven Vietnamese NLU recognition catalog."""

import json
from pathlib import Path
from typing import cast

import pytest

from app.dialog.nlu import (
    Intent,
    IntentCatalogLoader,
    InvalidIntentCatalogError,
    NLUEntityKind,
    NLUProcessor,
    NLUResolutionStatus,
    StateIntentPolicy,
    default_intent_catalog_path,
    load_default_intent_catalog,
    normalize_vietnamese,
)
from app.domain.booking_state import BookingState


def _raw_catalog() -> dict[str, object]:
    document = cast(
        dict[str, object],
        json.loads(default_intent_catalog_path().read_text(encoding="utf-8")),
    )
    return cast(dict[str, object], document["intent_catalog"])


def _write_catalog(tmp_path: Path, raw: dict[str, object]) -> Path:
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return path


def test_default_catalog_is_complete_immutable_and_cached_once() -> None:
    first = load_default_intent_catalog()
    second = load_default_intent_catalog()

    assert first is second
    assert {entry.intent for entry in first.entries} == set(Intent)
    assert isinstance(first.entries, tuple)
    assert all(isinstance(entry.examples, tuple) for entry in first.entries)
    assert all(isinstance(entry.allowed_states, frozenset) for entry in first.entries)


def test_every_catalog_example_maps_to_its_declared_intent() -> None:
    catalog = load_default_intent_catalog()

    for entry in catalog.entries:
        state = next(iter(entry.allowed_states))
        for example in entry.examples:
            matched = catalog.match(example, state)
            assert matched is not None, (entry.intent, example)
            assert matched.intent is entry.intent, (entry.intent, example, matched.intent)


@pytest.mark.parametrize(
    ("text", "state", "intent"),
    [
        ("xin chào", BookingState.IDLE, Intent.GREETING),
        ("chào Kori", BookingState.IDLE, Intent.GREETING),
        ("tôi muốn đặt lịch", BookingState.IDLE, Intent.START_BOOKING),
        ("tôi muốn đặt booking", BookingState.IDLE, Intent.START_BOOKING),
        ("book lịch giúp tôi", BookingState.IDLE, Intent.START_BOOKING),
        ("đặt chỗ cho ngày mai", BookingState.IDLE, Intent.START_BOOKING),
        ("có những liệu trình nào", BookingState.IDLE, Intent.LIST_SERVICES),
        (
            "liệt kê liệu trình chính và add-on",
            BookingState.SELECTING_SERVICE,
            Intent.LIST_SERVICES,
        ),
        ("Massage đá nóng 60 phút", BookingState.SELECTING_SERVICE, Intent.SELECT_SERVICE),
        ("4 người", BookingState.SELECTING_PEOPLE, Intent.SELECT_PEOPLE),
        ("60", BookingState.SELECTING_DURATION, Intent.SELECT_DURATION),
    ],
)
def test_required_catalog_examples(
    text: str,
    state: BookingState,
    intent: Intent,
) -> None:
    matched = load_default_intent_catalog().match(text, state)

    assert matched is not None
    assert matched.intent is intent


def test_numeric_duration_is_state_constrained() -> None:
    catalog = load_default_intent_catalog()

    assert catalog.match("60", BookingState.SELECTING_DURATION) is not None
    assert catalog.match("60", BookingState.IDLE) is None


def test_greeting_is_resolved_deterministically_when_unknowns_use_llm() -> None:
    parser = NLUProcessor(
        intent_policy=StateIntentPolicy(
            {BookingState.IDLE: frozenset({"greeting", "unknown"})},
            frozenset({BookingState.IDLE}),
        ),
        unknown_as_unresolved=True,
    )

    result = parser.parse(text="xin chào", state=BookingState.IDLE)

    assert result.intent == "greeting"
    assert result.resolution_status is NLUResolutionStatus.RESOLVED
    assert result.matched_rule == "catalog_greeting"


@pytest.mark.parametrize(
    ("text", "state", "intent", "payload"),
    [
        ("tôi muốn xem cửa hàng", BookingState.IDLE, "list_shops", {}),
        ("có những cửa hàng nào", BookingState.IDLE, "list_shops", {}),
        ("liệt kê chi nhánh cho tôi", BookingState.SELECTING_SHOP, "list_shops", {}),
        (
            "có cơ sở nào ở Huế",
            BookingState.SELECTING_SHOP,
            "search_shops",
            {"location_query": "huế"},
        ),
        (
            "có những liệu trình nào",
            BookingState.SELECTING_SERVICE,
            "list_services",
            {},
        ),
        (
            "có những giờ nào trống",
            BookingState.SELECTING_TIME,
            "list_available_times",
            {},
        ),
        (
            "có những kỹ thuật viên nào",
            BookingState.SELECTING_THERAPIST,
            "list_therapists",
            {},
        ),
    ],
)
def test_discovery_phrases_dispatch_without_entity_selection(
    text: str,
    state: BookingState,
    intent: str,
    payload: dict[str, object],
) -> None:
    parser = NLUProcessor(
        intent_policy=StateIntentPolicy(
            {state: frozenset({intent, "unknown"})},
            frozenset(),
        ),
        unknown_as_unresolved=True,
    )

    result = parser.parse(text=text, state=state)

    assert result.intent == intent
    assert result.payload == payload
    assert result.entity_kind is None
    assert result.resolution_status is NLUResolutionStatus.RESOLVED


def test_specific_shop_name_remains_entity_selection() -> None:
    parser = NLUProcessor(
        intent_policy=StateIntentPolicy(
            {BookingState.SELECTING_SHOP: frozenset({"select_store", "list_shops"})},
            frozenset(),
        )
    )

    result = parser.parse(text="Komorebi Huế", state=BookingState.SELECTING_SHOP)

    assert result.intent is None
    assert result.entity_kind is NLUEntityKind.SHOP
    assert result.entity_query == "komorebi huế"


def test_priority_and_exclusions_prevent_catalog_inquiry_conflicts() -> None:
    catalog = load_default_intent_catalog()

    inquiry = catalog.match(
        "bạn liệt kê cho tôi xem liệu trình chính và addon được không",
        BookingState.SELECTING_SERVICE,
    )
    selection = catalog.match(
        "chọn Massage đá nóng 60 phút",
        BookingState.SELECTING_SERVICE,
    )

    assert inquiry is not None and inquiry.intent is Intent.LIST_SERVICES
    assert selection is not None and selection.intent is Intent.SELECT_SERVICE


def test_normalization_is_unicode_safe_and_typo_is_service_scoped() -> None:
    decomposed = "xin cha\u0300o"

    assert normalize_vietnamese(decomposed) == "xin chào"
    assert normalize_vietnamese("ADD-ON, add_on addon") == "add on add_on add on"
    assert normalize_vietnamese("lộ trình", course_context=True) == "liệu trình"
    assert normalize_vietnamese("lộ trình") == "lộ trình"
    matched = load_default_intent_catalog().match(
        "liệt kê lộ trình chính và add on",
        BookingState.SELECTING_SERVICE,
    )
    assert matched is not None and matched.intent is Intent.LIST_SERVICES


def test_loader_rejects_duplicate_intent(tmp_path: Path) -> None:
    raw = _raw_catalog()
    intents = raw["intents"]
    assert isinstance(intents, list)
    intents.append(dict(intents[0]))

    with pytest.raises(InvalidIntentCatalogError, match="Duplicate intent"):
        IntentCatalogLoader.load(_write_catalog(tmp_path, raw))


def test_loader_rejects_unknown_intent(tmp_path: Path) -> None:
    raw = _raw_catalog()
    intents = raw["intents"]
    assert isinstance(intents, list) and isinstance(intents[0], dict)
    intents[0]["intent"] = "invented"

    with pytest.raises(InvalidIntentCatalogError, match="unknown intent"):
        IntentCatalogLoader.load(_write_catalog(tmp_path, raw))


def test_loader_rejects_unknown_state(tmp_path: Path) -> None:
    raw = _raw_catalog()
    intents = raw["intents"]
    assert isinstance(intents, list) and isinstance(intents[0], dict)
    intents[0]["allowed_states"] = ["invented"]

    with pytest.raises(InvalidIntentCatalogError, match="unknown state"):
        IntentCatalogLoader.load(_write_catalog(tmp_path, raw))


def test_loader_rejects_empty_phrase(tmp_path: Path) -> None:
    raw = _raw_catalog()
    intents = raw["intents"]
    assert isinstance(intents, list) and isinstance(intents[0], dict)
    intents[0]["exact_phrases"] = [" "]

    with pytest.raises(InvalidIntentCatalogError, match="non-empty string"):
        IntentCatalogLoader.load(_write_catalog(tmp_path, raw))
