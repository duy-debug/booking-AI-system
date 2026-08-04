"""Deterministic and LLM-backed intent and entity parsing for dialog input."""

import json
import re
import unicodedata
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, time, timedelta
from enum import StrEnum
from math import isfinite
from types import MappingProxyType
from typing import Literal, TypeAlias

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
)

from app.application.ports.llm_gateway import LLMGateway, LLMGatewayError, LLMMessage
from app.dialog.dialog_controller import DialogTurnInput
from app.dialog.flow_loader import FlowDefinition
from app.dialog.nlu_catalog import (
    Intent,
    IntentCatalog,
    load_default_intent_catalog,
    normalize_vietnamese,
)
from app.domain.booking import CourseSelection, Shop
from app.domain.booking_state import BookingState

TodayProvider: TypeAlias = Callable[[], date]
BookingChangeTarget: TypeAlias = Literal[
    "shop",
    "date",
    "people",
    "duration",
    "service",
    "time",
    "therapist",
    "phone",
]

LLM_NLU_MIN_CONFIDENCE = 0.70
FAQ_ALLOWED_STATES = frozenset(
    {
        BookingState.IDLE,
        BookingState.SELECTING_SHOP,
        BookingState.SELECTING_DATE,
        BookingState.SELECTING_PEOPLE,
        BookingState.SELECTING_DURATION,
        BookingState.SELECTING_SERVICE,
        BookingState.SELECTING_TIME,
        BookingState.SELECTING_THERAPIST,
        BookingState.COLLECTING_PHONE,
        BookingState.VERIFYING_PHONE,
        BookingState.AWAITING_CONFIRMATION,
        BookingState.COMPLETED,
        BookingState.CANCELLED,
    }
)
DISCOVERY_ALLOWED_STATES: Mapping[str, frozenset[BookingState]] = MappingProxyType(
    {
        "list_shops": frozenset(BookingState),
        "search_shops": frozenset(BookingState),
        "list_services": frozenset(
            BookingState
        ),
        "list_addons": frozenset(
            BookingState
        ),
        "list_available_times": frozenset(
            BookingState
        ),
        "list_therapists": frozenset(
            BookingState
        ),
    }
)

_RULE_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
_WHITESPACE_PATTERN = re.compile(r"\s+")
_PUNCTUATION_PATTERN = re.compile(r'[.,!?;()\[\]{}"]')
_PEOPLE_NUMERIC_PATTERN = re.compile(r"(?<!\d)(\d{1,2})\s*người\b")
_PEOPLE_WORD_PATTERN = re.compile(r"\b(một|hai|ba)\s+người\b")
_MINUTES_PATTERN = re.compile(r"(?<!\d)(\d{1,3})\s*phút\b")
_HOURS_PATTERN = re.compile(
    r"(?<!\d)(\d{1,2})\s*(?:giờ|tiếng)(\s+rưỡi)?\b"
    r"(?!\s*(?:sáng|trưa|chiều|tối))"
)
_ISO_DATE_PATTERN = re.compile(r"(?<!\d)(\d{4})-(\d{1,2})-(\d{1,2})(?!\d)")
_SLASH_DATE_PATTERN = re.compile(r"(?<!\d)(\d{1,2})/(\d{1,2})(?:/(\d{4}))?(?!\d)")
_CLOCK_PATTERN = re.compile(
    r"(?<!\d)(\d{1,2})(?::(\d{2})|h(\d{2})?|\s+giờ)"
    r"(?:\s*(sáng|trưa|chiều|tối))?(?!\w)"
)
_PHONE_PATTERN = re.compile(r"(?<![\w+])(\+?\d(?:[\s-]?\d){8,14})(?!\w)")
_COURSE_DURATION_PATTERN = re.compile(
    r"(?<!\d)(?:\d{1,3}\s*phút|\d{1,2}\s*(?:giờ|tiếng)(?:\s+rưỡi)?)(?!\w)"
)

_CANCEL_PHRASES = frozenset(
    {"hủy", "hủy đặt lịch", "dừng đặt lịch", "thôi không đặt nữa"}
)
_RESTART_PHRASES = frozenset({"đặt lại từ đầu", "bắt đầu lại", "restart booking"})
_WHY_PHRASES = frozenset(
    {
        "tại sao",
        "vì sao",
        "sao lại thế",
        "tôi phải làm gì tiếp theo",
        "bạn đang cần tôi nhập gì",
    }
)
_REPEAT_PHRASES = frozenset({"nhắc lại", "hỏi lại đi", "lặp lại câu hỏi", "thử lại"})
_QUESTION_PREFIXES = (
    "ai ",
    "gì ",
    "tại sao ",
    "vì sao ",
    "khi nào ",
    "ở đâu ",
    "bao nhiêu ",
    "như thế nào ",
    "có thể ",
)


class NLUSource(StrEnum):
    """Identifies whether a result came from rules or the safe fallback."""

    DETERMINISTIC = "deterministic"
    FALLBACK = "fallback"


class NLUResolutionStatus(StrEnum):
    """Describes whether an NLU result is safe to dispatch."""

    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"
    ENTITY_RESOLUTION_REQUIRED = "entity_resolution_required"


class NLUEntityKind(StrEnum):
    """Identifies an entity query that needs an authoritative resolver."""

    SHOP = "shop"
    COURSE = "course"
    THERAPIST = "therapist"


class NLUResultNotDispatchableError(Exception):
    """Raised when an NLU result cannot safely become a dialog turn."""


@dataclass(frozen=True, slots=True)
class StateIntentPolicy:
    """Contains immutable named-intent and wildcard availability by state."""

    allowed_intents: Mapping[BookingState, frozenset[str]]
    wildcard_states: frozenset[BookingState]

    def __post_init__(self) -> None:
        copied: dict[BookingState, frozenset[str]] = {}
        for state, intents in self.allowed_intents.items():
            if not isinstance(state, BookingState):
                raise TypeError("Intent policy keys must be BookingState values.")
            named = frozenset(intents)
            if "*" in named:
                raise ValueError("Wildcard must not be stored as a named intent.")
            if any(not isinstance(intent, str) or not intent for intent in named):
                raise ValueError("Named intents must be non-empty strings.")
            copied[state] = named
        wildcard_states = frozenset(self.wildcard_states)
        if any(not isinstance(state, BookingState) for state in wildcard_states):
            raise TypeError("Wildcard states must be BookingState values.")
        object.__setattr__(self, "allowed_intents", MappingProxyType(copied))
        object.__setattr__(self, "wildcard_states", wildcard_states)

    def allowed_for(self, state: BookingState) -> frozenset[str]:
        """Return named intents accepted by one state."""
        return self.allowed_intents.get(state, frozenset())

    def is_allowed(self, state: BookingState, intent: str) -> bool:
        """Return whether an exact named intent is accepted by one state."""
        return intent in self.allowed_for(state)

    def has_wildcard(self, state: BookingState) -> bool:
        """Return whether a state declares a separate wildcard transition."""
        return state in self.wildcard_states


def build_state_intent_policy(
    flow: FlowDefinition,
    *,
    enable_faq: bool = False,
    enable_discovery: bool = False,
) -> StateIntentPolicy:
    """Copy named intents and wildcard availability from an already loaded flow."""
    allowed: dict[BookingState, frozenset[str]] = {}
    wildcard_states: set[BookingState] = set()
    for state, definition in flow.states.items():
        intents = {transition.intent for transition in definition.transitions}
        if "*" in intents:
            wildcard_states.add(state)
        allowed[state] = frozenset(intent for intent in intents if intent != "*")
    if enable_faq:
        for state in FAQ_ALLOWED_STATES:
            allowed[state] = allowed.get(state, frozenset()) | {"ask_question"}
    if enable_discovery:
        for intent, states in DISCOVERY_ALLOWED_STATES.items():
            for state in states:
                allowed[state] = allowed.get(state, frozenset()) | {intent}
    return StateIntentPolicy(allowed, frozenset(wildcard_states))


@dataclass(frozen=True, slots=True)
class NLUResult:
    """Contains one immutable parsed intent and its typed entities."""

    intent: str | None
    payload: Mapping[str, object]
    confidence: float
    source: NLUSource
    resolution_status: NLUResolutionStatus
    matched_rule: str | None = None
    entity_query: str | None = None
    entity_kind: NLUEntityKind | None = None
    change_target: BookingChangeTarget | None = None
    has_unconsumed_entities: bool = False

    def __post_init__(self) -> None:
        if self.intent is not None and (
            not isinstance(self.intent, str) or not self.intent.strip()
        ):
            raise ValueError("Resolved NLU intent must be a non-empty string.")
        if (
            isinstance(self.confidence, bool)
            or not isinstance(self.confidence, int | float)
            or not isfinite(self.confidence)
            or not 0.0 <= self.confidence <= 1.0
        ):
            raise ValueError("NLU confidence must be between zero and one.")
        if not isinstance(self.source, NLUSource):
            raise TypeError("NLU source must be an NLUSource value.")
        if not isinstance(self.resolution_status, NLUResolutionStatus):
            raise TypeError("NLU resolution status is invalid.")
        if self.matched_rule is not None and not _RULE_NAME_PATTERN.fullmatch(
            self.matched_rule
        ):
            raise ValueError("Matched rule must be a safe snake_case identifier.")
        if not isinstance(self.has_unconsumed_entities, bool):
            raise TypeError("Unconsumed-entity marker must be boolean.")
        self._validate_resolution_shape()
        if self.intent is not None:
            object.__setattr__(self, "intent", self.intent.strip())
        object.__setattr__(self, "confidence", float(self.confidence))
        object.__setattr__(self, "payload", _freeze_mapping(self.payload))
        if self.entity_query is not None:
            object.__setattr__(self, "entity_query", self.entity_query.strip())

    def is_dispatchable(self) -> bool:
        """Return whether the result has the basic shape required for dispatch."""
        return (
            self.resolution_status is NLUResolutionStatus.RESOLVED
            and self.intent is not None
            and self.entity_query is None
            and self.entity_kind is None
        )

    def _validate_resolution_shape(self) -> None:
        if self.resolution_status is NLUResolutionStatus.RESOLVED:
            if self.intent is None:
                raise ValueError("Resolved NLU result requires an intent.")
            if (
                self.entity_query is not None
                or self.entity_kind is not None
                or self.change_target is not None
            ):
                raise ValueError("Resolved NLU result cannot contain an entity query.")
            return
        if self.intent is not None or self.payload:
            raise ValueError("Non-dispatchable NLU result cannot carry intent or payload.")
        if self.resolution_status is NLUResolutionStatus.ENTITY_RESOLUTION_REQUIRED:
            if (
                not isinstance(self.entity_query, str)
                or not self.entity_query.strip()
                or not isinstance(self.entity_kind, NLUEntityKind)
            ):
                raise ValueError("Entity resolution result requires a query and kind.")
            if self.change_target not in {None, "shop", "service"}:
                raise ValueError("Entity resolution change target is invalid.")
        elif (
            self.entity_query is not None
            or self.entity_kind is not None
            or self.change_target is not None
        ):
            raise ValueError("Unresolved NLU result cannot contain an entity query.")


class DeterministicNLU:
    """Parse high-confidence Vietnamese booking input using state-aware rules."""

    def __init__(
        self,
        *,
        intent_policy: StateIntentPolicy,
        today_provider: TodayProvider = date.today,
        unknown_as_unresolved: bool = False,
        catalog: IntentCatalog | None = None,
    ) -> None:
        if not isinstance(intent_policy, StateIntentPolicy):
            raise TypeError("Intent policy must be a StateIntentPolicy.")
        if not callable(today_provider):
            raise TypeError("Today provider must be callable.")
        if not isinstance(unknown_as_unresolved, bool):
            raise TypeError("Unknown fallback mode must be a boolean.")
        self._intent_policy = intent_policy
        self._today_provider = today_provider
        self._unknown_as_unresolved = unknown_as_unresolved
        self._catalog = catalog or load_default_intent_catalog()

    def parse(self, *, text: str, state: BookingState) -> NLUResult:
        """Return the first deterministic match according to rule precedence."""
        if not isinstance(text, str):
            raise TypeError("NLU text must be a string.")
        if not isinstance(state, BookingState):
            raise TypeError("NLU state must be a BookingState value.")
        normalized = _normalize_text(text)
        if not normalized:
            return _fallback(
                self._intent_policy,
                state,
                allow_unknown=not self._unknown_as_unresolved,
            )

        today = self._today_provider()
        if not isinstance(today, date):
            raise TypeError("Today provider must return a date.")
        catalog_match = self._catalog.match(text, state)
        unrestricted_catalog_match = self._catalog.match(text)

        if normalized in _CANCEL_PHRASES:
            return _resolved(
                self._intent_policy, state, "cancel_flow", {}, 1.0, "cancel_exact"
            )
        if normalized in _RESTART_PHRASES:
            return _globally_resolved("restart_booking", "restart_exact")

        change_catalog_match = (
            catalog_match is not None and catalog_match.intent is Intent.CHANGE_INFO
        ) or (
            unrestricted_catalog_match is not None
            and unrestricted_catalog_match.intent is Intent.CHANGE_INFO
        )
        if change_catalog_match:
            change_result = _parse_change_request(
                normalized,
                state=state,
                today=today,
                policy=self._intent_policy,
            )
            if change_result is not None:
                return change_result

        global_catalog_match = catalog_match or unrestricted_catalog_match
        if global_catalog_match is not None and global_catalog_match.intent in {
            Intent.GREETING,
            Intent.THANKS,
        }:
            return _globally_resolved(
                global_catalog_match.intent.value,
                f"catalog_{global_catalog_match.intent.value}",
            )

        if global_catalog_match is not None and global_catalog_match.intent in {
            Intent.FAQ,
        }:
            return _resolved(
                self._intent_policy,
                state,
                "ask_question",
                {"query": text.strip()},
                0.95,
                "faq_explicit",
            )

        if global_catalog_match is not None and global_catalog_match.intent in {
            Intent.LIST_SHOPS,
            Intent.SEARCH_SHOPS,
            Intent.LIST_SERVICES,
            Intent.LIST_ADDONS,
            Intent.LIST_AVAILABLE_TIMES,
            Intent.LIST_THERAPISTS,
        }:
            payload: dict[str, object] = {}
            if global_catalog_match.intent is Intent.SEARCH_SHOPS:
                location_query = _extract_location_query(normalized)
                if location_query is None:
                    return _unresolved(
                        source=NLUSource.DETERMINISTIC,
                        matched_rule="catalog_search_shops",
                    )
                payload["location_query"] = location_query
            return _resolved(
                self._intent_policy,
                state,
                global_catalog_match.intent.value,
                payload,
                0.95,
                f"catalog_{global_catalog_match.intent.value}",
            )
        if normalized in _WHY_PHRASES:
            return _globally_resolved("ask_why", "ask_why_exact")
        if normalized in _REPEAT_PHRASES:
            return _globally_resolved("repeat_last_question", "repeat_exact")

        scalar_result = self._parse_scalar_for_state(normalized, state, today)
        if scalar_result is not None:
            return scalar_result

        if catalog_match is not None and catalog_match.intent is Intent.START_BOOKING:
            booking_date, _ = _extract_date(normalized, today)
            return _resolved(
                self._intent_policy,
                state,
                "start_booking",
                {},
                0.95,
                "start_booking_phrase",
                has_unconsumed_entities=booking_date is not None,
            )

        correction = state is BookingState.SELECTING_PEOPLE and " mà " in normalized
        if correction:
            people = _extract_people(normalized, allow_bare=False, take_last=True)
            if people is not None:
                return _resolved(
                    self._intent_policy,
                    state,
                    "select_people",
                    {"num_customer": people},
                    0.95,
                    "people_correction",
                )

        if catalog_match is not None and catalog_match.intent is Intent.CONFIRM:
            return _resolved(
                self._intent_policy,
                state,
                "confirm",
                {},
                1.0,
                "confirm_exact",
            )
        if catalog_match is not None and catalog_match.intent is Intent.DENY:
            return _resolved(
                self._intent_policy,
                state,
                "deny",
                {},
                1.0,
                "deny_exact",
            )

        state_restricted_intents = {
            Intent.START_BOOKING,
            Intent.CONFIRM,
            Intent.DENY,
            Intent.GREETING,
            Intent.THANKS,
        }
        if (
            catalog_match is None
            and unrestricted_catalog_match is not None
            and unrestricted_catalog_match.intent in state_restricted_intents
        ):
            is_shop_selection = (
                state is BookingState.SELECTING_SHOP
                and unrestricted_catalog_match.intent is Intent.START_BOOKING
                and _looks_like_shop_selection(normalized)
            )
            if not is_shop_selection:
                return _unresolved(
                    source=NLUSource.DETERMINISTIC,
                    matched_rule=(
                        f"catalog_{unrestricted_catalog_match.intent.value}_disallowed"
                    ),
                )

        state_result = self._parse_entity_for_state(normalized, state)
        if state_result is not None:
            return state_result

        if catalog_match is not None and catalog_match.intent in {
            Intent.GREETING,
            Intent.THANKS,
        }:
            return _resolved(
                self._intent_policy,
                state,
                catalog_match.intent.value,
                {},
                1.0,
                f"catalog_{catalog_match.intent.value}",
            )
        if _looks_like_question(text, normalized):
            return _unresolved(
                confidence=0.0,
                source=NLUSource.FALLBACK,
                matched_rule="question_unresolved",
            )
        return _fallback(
            self._intent_policy,
            state,
            allow_unknown=not self._unknown_as_unresolved,
        )

    def _parse_scalar_for_state(
        self,
        text: str,
        state: BookingState,
        today: date,
    ) -> NLUResult | None:
        if state is BookingState.SELECTING_PEOPLE:
            if text.startswith("không phải "):
                return None
            people = _extract_people(text, allow_bare=True)
            if people is not None:
                people_payload: dict[str, object] = {"num_customer": people}
                return _resolved(
                    self._intent_policy,
                    state,
                    "select_people",
                    people_payload,
                    0.95,
                    "people_numeric",
                    has_unconsumed_entities=_has_secondary_entities(
                        text, today, primary="num_customer"
                    ),
                )

        if state in {BookingState.SELECTING_DURATION, BookingState.SELECTING_SERVICE}:
            duration, rule = _extract_duration(text, allow_bare=True)
            if (
                duration is not None
                and rule is not None
                and (
                    state is BookingState.SELECTING_DURATION
                    or _is_duration_correction(text)
                )
            ):
                duration_payload: dict[str, object] = {
                    "duration_minutes": duration
                }
                return _resolved(
                    self._intent_policy,
                    state,
                    "select_duration",
                    duration_payload,
                    0.95,
                    rule,
                    has_unconsumed_entities=_has_secondary_entities(
                        text, today, primary="duration_minutes"
                    ),
                )

        if state is BookingState.SELECTING_DATE:
            booking_date, rule = _extract_date(text, today)
            if booking_date is not None and rule is not None:
                date_payload: dict[str, object] = {"booking_date": booking_date}
                return _resolved(
                    self._intent_policy,
                    state,
                    "select_date",
                    date_payload,
                    0.95,
                    rule,
                    has_unconsumed_entities=_has_secondary_entities(
                        text, today, primary="booking_date"
                    ),
                )

        if state in {BookingState.SELECTING_TIME, BookingState.BOOKING_FAILED}:
            start_time = _extract_time(text)
            if start_time is not None:
                time_payload: dict[str, object] = {"start_time": start_time}
                return _resolved(
                    self._intent_policy,
                    state,
                    "select_time",
                    time_payload,
                    0.95,
                    "explicit_time",
                    has_unconsumed_entities=_has_secondary_entities(
                        text, today, primary="start_time"
                    ),
                )

        if state in {BookingState.COLLECTING_PHONE, BookingState.VERIFYING_PHONE}:
            phone = _extract_phone(text)
            if phone is not None:
                return _resolved(
                    self._intent_policy,
                    state,
                    "provide_phone",
                    {"phone": phone},
                    0.95,
                    "phone_candidate",
                )

        return None

    def _parse_entity_for_state(
        self,
        text: str,
        state: BookingState,
    ) -> NLUResult | None:
        if state is BookingState.SELECTING_SHOP:
            query = _extract_shop_query(text)
            if query is not None:
                return _entity_required(
                    self._intent_policy,
                    state,
                    required_intent="select_store",
                    query=query,
                    kind=NLUEntityKind.SHOP,
                    confidence=0.8,
                    matched_rule="shop_query_state",
                )

        if state is BookingState.SELECTING_SERVICE:
            query = _extract_course_query(text)
            if query is not None:
                duration, _ = _extract_duration(text, allow_bare=False)
                return _entity_required(
                    self._intent_policy,
                    state,
                    required_intent="select_course",
                    query=query,
                    kind=NLUEntityKind.COURSE,
                    confidence=0.8,
                    matched_rule="course_query_state",
                    has_unconsumed_entities=duration is not None,
                )

        if state is BookingState.SELECTING_THERAPIST:
            return _extract_therapist_result(text, self._intent_policy, state)
        return None


def to_dialog_turn_input(
    result: NLUResult,
    *,
    state: BookingState,
    intent_policy: StateIntentPolicy,
    idempotency_key: str | None = None,
    raw_message: str | None = None,
) -> DialogTurnInput:
    """Map only a policy-valid and payload-safe result to a dialog turn."""
    if not result.is_dispatchable() or result.intent is None:
        raise NLUResultNotDispatchableError("NLU result is not resolved for dispatch.")
    if not intent_policy.is_allowed(state, result.intent):
        raise NLUResultNotDispatchableError(
            "NLU intent is not allowed in the current state."
        )
    _validate_dispatch_payload(result.intent, result.payload)
    return DialogTurnInput(
        intent=result.intent,
        payload=result.payload,
        idempotency_key=idempotency_key,
        raw_message=raw_message,
    )


def _normalize_text(text: str) -> str:
    lowered = unicodedata.normalize("NFC", text).casefold().strip()
    punctuation_normalized = _PUNCTUATION_PATTERN.sub(" ", lowered)
    return _WHITESPACE_PATTERN.sub(" ", punctuation_normalized).strip()


def _resolved(
    policy: StateIntentPolicy,
    state: BookingState,
    intent: str,
    payload: Mapping[str, object],
    confidence: float,
    matched_rule: str,
    *,
    has_unconsumed_entities: bool = False,
) -> NLUResult:
    if not policy.is_allowed(state, intent):
        return _unresolved(
            confidence=confidence,
            source=NLUSource.DETERMINISTIC,
            matched_rule=matched_rule,
            has_unconsumed_entities=has_unconsumed_entities,
        )
    return NLUResult(
        intent=intent,
        payload=payload,
        confidence=confidence,
        source=NLUSource.DETERMINISTIC,
        resolution_status=NLUResolutionStatus.RESOLVED,
        matched_rule=matched_rule,
        has_unconsumed_entities=has_unconsumed_entities,
    )


def _globally_resolved(intent: str, matched_rule: str) -> NLUResult:
    """Build a transport-handled intent that is valid independently of flow state."""
    return NLUResult(
        intent=intent,
        payload={},
        confidence=1.0,
        source=NLUSource.DETERMINISTIC,
        resolution_status=NLUResolutionStatus.RESOLVED,
        matched_rule=matched_rule,
    )


def _is_duration_correction(text: str) -> bool:
    stripped = _strip_prefixes(
        text,
        ("đổi sang ", "đổi thời lượng sang ", "chọn "),
    )
    return bool(re.fullmatch(r"\d{1,3}(?:\s*phút)?", stripped))


def _fallback(
    policy: StateIntentPolicy,
    state: BookingState,
    *,
    allow_unknown: bool = True,
) -> NLUResult:
    if allow_unknown and policy.is_allowed(state, "unknown"):
        return NLUResult(
            intent="unknown",
            payload={},
            confidence=0.0,
            source=NLUSource.FALLBACK,
            resolution_status=NLUResolutionStatus.RESOLVED,
        )
    return _unresolved()


def _unresolved(
    *,
    confidence: float = 0.0,
    source: NLUSource = NLUSource.FALLBACK,
    matched_rule: str | None = None,
    has_unconsumed_entities: bool = False,
) -> NLUResult:
    return NLUResult(
        intent=None,
        payload={},
        confidence=confidence,
        source=source,
        resolution_status=NLUResolutionStatus.UNRESOLVED,
        matched_rule=matched_rule,
        has_unconsumed_entities=has_unconsumed_entities,
    )


def _entity_required(
    policy: StateIntentPolicy,
    state: BookingState,
    *,
    required_intent: str,
    query: str,
    kind: NLUEntityKind,
    confidence: float,
    matched_rule: str,
    has_unconsumed_entities: bool = False,
    change_target: BookingChangeTarget | None = None,
) -> NLUResult:
    if not policy.is_allowed(state, required_intent):
        return _unresolved(
            confidence=confidence,
            source=NLUSource.DETERMINISTIC,
            matched_rule=matched_rule,
            has_unconsumed_entities=has_unconsumed_entities,
        )
    return NLUResult(
        intent=None,
        payload={},
        confidence=confidence,
        source=NLUSource.DETERMINISTIC,
        resolution_status=NLUResolutionStatus.ENTITY_RESOLUTION_REQUIRED,
        matched_rule=matched_rule,
        entity_query=query,
        entity_kind=kind,
        change_target=change_target,
        has_unconsumed_entities=has_unconsumed_entities,
    )


def _parse_change_request(
    text: str,
    *,
    state: BookingState,
    today: date,
    policy: StateIntentPolicy,
) -> NLUResult | None:
    target = _change_target(text)
    if target is None:
        return None

    payload: dict[str, object] = {"change_target": target}
    if target == "date":
        booking_date, _ = _extract_date(text, today)
        if booking_date is not None:
            payload["booking_date"] = booking_date
    elif target == "people":
        people = _extract_people(text, allow_bare=False)
        if people is not None:
            payload["num_customer"] = people
    elif target == "duration":
        duration, _ = _extract_duration(text, allow_bare=False)
        if duration is not None:
            payload["duration_minutes"] = duration
    elif target == "time":
        start_time = _extract_time(text)
        if start_time is not None:
            payload["start_time"] = start_time
    elif target == "therapist":
        gender = _change_therapist_gender(text)
        if gender is not None:
            payload["therapist_gender"] = gender
    elif target == "phone":
        phone = _extract_phone(text)
        if phone is not None:
            payload["phone"] = phone
    elif target in {"shop", "service"}:
        query = _change_entity_query(text, target)
        if query is not None:
            return _entity_required(
                policy,
                state,
                required_intent="change_info",
                query=query,
                kind=(
                    NLUEntityKind.SHOP
                    if target == "shop"
                    else NLUEntityKind.COURSE
                ),
                confidence=0.95,
                matched_rule="change_entity_query",
                change_target=target,
            )
    return _resolved(
        policy,
        state,
        "change_info",
        payload,
        0.95,
        "change_booking_field",
    )


def _change_target(text: str) -> BookingChangeTarget | None:
    if "số điện thoại" in text:
        return "phone"
    if "kỹ thuật viên" in text:
        return "therapist"
    if "cửa hàng" in text or "chi nhánh" in text:
        return "shop"
    if "liệu trình" in text or "dịch vụ" in text:
        return "service"
    if "ngày" in text:
        return "date"
    if "số người" in text or _extract_people(text, allow_bare=False) is not None:
        return "people"
    duration, _ = _extract_duration(text, allow_bare=False)
    if "thời lượng" in text or duration is not None:
        return "duration"
    if "khung giờ" in text or "giờ" in text:
        return "time"
    return None


def _change_entity_query(
    text: str,
    target: Literal["shop", "service"],
) -> str | None:
    query = _strip_prefixes(
        text,
        ("tôi muốn đổi ", "đổi sang ", "đổi ", "chọn lại ", "chọn "),
    )
    prefixes = (
        ("chi nhánh ", "cửa hàng ")
        if target == "shop"
        else ("liệu trình ", "dịch vụ ")
    )
    query = _strip_prefixes(query, prefixes)
    return (
        None
        if query in {"", "khác", "cửa hàng", "chi nhánh", "liệu trình", "dịch vụ"}
        else query
    )


def _change_therapist_gender(text: str) -> Literal["male", "female", "none"] | None:
    if "không yêu cầu" in text or "không chọn" in text:
        return "none"
    if text.endswith(" nam"):
        return "male"
    if text.endswith(" nữ"):
        return "female"
    return None


def _extract_people(
    text: str,
    *,
    allow_bare: bool,
    take_last: bool = False,
) -> int | None:
    numeric = [int(match.group(1)) for match in _PEOPLE_NUMERIC_PATTERN.finditer(text)]
    words = {"một": 1, "hai": 2, "ba": 3}
    word_values = [words[match.group(1)] for match in _PEOPLE_WORD_PATTERN.finditer(text)]
    candidates = numeric + word_values
    if candidates:
        if len(candidates) > 1 and not take_last:
            return None
        return candidates[-1] if take_last else candidates[0]
    if allow_bare and re.fullmatch(r"\d{1,2}", text):
        return int(text)
    if allow_bare and text in words:
        return words[text]
    return None


def _extract_duration(
    text: str,
    *,
    allow_bare: bool,
) -> tuple[int | None, str | None]:
    minute_match = _MINUTES_PATTERN.search(text)
    if minute_match is not None:
        return int(minute_match.group(1)), "duration_minutes"
    hour_match = _HOURS_PATTERN.search(text)
    if hour_match is not None:
        minutes = int(hour_match.group(1)) * 60
        if hour_match.group(2) is not None:
            minutes += 30
        return minutes, "duration_hours"
    if allow_bare and re.fullmatch(r"\d{1,3}", text):
        return int(text), "duration_numeric"
    return None, None


def _extract_date(
    text: str,
    today: date,
) -> tuple[date | None, str | None]:
    relative_offsets = (("ngày kia", 2), ("ngày mai", 1), ("hôm nay", 0))
    for phrase, offset in relative_offsets:
        if phrase in text:
            return today + timedelta(days=offset), "relative_date"

    iso_match = _ISO_DATE_PATTERN.search(text)
    if iso_match is not None:
        return _safe_date(
            int(iso_match.group(1)),
            int(iso_match.group(2)),
            int(iso_match.group(3)),
            "iso_date",
        )
    slash_match = _SLASH_DATE_PATTERN.search(text)
    if slash_match is not None:
        year = int(slash_match.group(3)) if slash_match.group(3) else today.year
        return _safe_date(
            year,
            int(slash_match.group(2)),
            int(slash_match.group(1)),
            "slash_date",
        )
    return None, None


def _safe_date(
    year: int,
    month: int,
    day: int,
    rule: str,
) -> tuple[date | None, str | None]:
    try:
        return date(year, month, day), rule
    except ValueError:
        return None, None


def _extract_time(text: str) -> time | None:
    matches = tuple(_CLOCK_PATTERN.finditer(text))
    if len(matches) != 1:
        return None
    match = matches[0]
    hour = int(match.group(1))
    minute_text = match.group(2) or match.group(3)
    minute = int(minute_text) if minute_text is not None else 0
    period = match.group(4)
    if minute > 59:
        return None
    if period is None:
        if match.group(2) is None and hour <= 12:
            return None
    else:
        hour = _apply_vietnamese_period(hour, period)
        if hour < 0:
            return None
    if not 0 <= hour <= 23:
        return None
    return time(hour, minute)


def _apply_vietnamese_period(hour: int, period: str) -> int:
    if not 1 <= hour <= 12:
        return -1
    if period == "sáng":
        return 0 if hour == 12 else hour
    if period == "trưa":
        return hour if hour >= 11 else hour + 12
    return hour if hour == 12 else hour + 12


def _extract_phone(text: str) -> str | None:
    matches = tuple(_PHONE_PATTERN.finditer(text))
    if len(matches) != 1:
        return None
    candidate = re.sub(r"[\s-]", "", matches[0].group(1))
    digit_count = len(candidate.removeprefix("+"))
    if not 9 <= digit_count <= 15:
        return None
    return candidate


def _extract_shop_query(text: str) -> str | None:
    query = _strip_prefixes(
        text,
        (
            "tôi muốn đặt cửa hàng ",
            "tôi muốn đặt chi nhánh ",
            "tôi muốn đặt tại ",
            "tôi muốn đặt ở ",
            "tôi muốn đặt bên ",
            "tôi muốn đặt ",
            "tôi muốn chọn ",
            "tôi chọn cửa hàng ",
            "tôi chọn chi nhánh ",
            "cho tôi cửa hàng ",
            "cho tôi chi nhánh ",
            "cho mình cửa hàng ",
            "cho mình chi nhánh ",
            "đặt cửa hàng ",
            "đặt chi nhánh ",
            "đặt tại ",
            "đặt ở ",
            "chọn ",
            "chi nhánh ",
            "cửa hàng ",
        ),
    )
    query = _strip_prefixes(query, ("chi nhánh ", "cửa hàng "))
    query = _strip_suffixes(
        query,
        (" giúp mình", " giúp tôi", " cho mình", " cho tôi", " nhé", " nha", " ạ"),
    )
    return query or None


def _looks_like_shop_selection(text: str) -> bool:
    return (
        "komorebi" in text
        or "chi nhánh" in text
        or "cửa hàng" in text
        or text.startswith(("đặt ở ", "đặt tại ", "đặt bên "))
    )


def _extract_course_query(text: str) -> str | None:
    text = normalize_vietnamese(text, service_context=True)
    without_duration = _COURSE_DURATION_PATTERN.sub(" ", text)
    query = _WHITESPACE_PATTERN.sub(" ", without_duration).strip()
    query = _strip_prefixes(
        query,
        ("tôi muốn chọn ", "tôi muốn ", "chọn ", "liệu trình "),
    )
    return query or None


def _extract_location_query(text: str) -> str | None:
    marker = " ở "
    if marker not in f" {text} ":
        return None
    query = text.rsplit(marker, 1)[-1].strip()
    query = _strip_prefixes(query, ("khu vực ", "tỉnh ", "thành phố "))
    return query or None


def _extract_therapist_result(
    text: str,
    policy: StateIntentPolicy,
    state: BookingState,
) -> NLUResult | None:
    if text in {"không yêu cầu", "ai cũng được", "không chọn"}:
        return _resolved(
            policy,
            state,
            "deny",
            {},
            1.0,
            "therapist_none_exact",
        )
    if text in {"nam", "kỹ thuật viên nam"}:
        return _entity_required(
            policy,
            state,
            required_intent="select_therapist",
            query="male",
            kind=NLUEntityKind.THERAPIST,
            confidence=1.0,
            matched_rule="therapist_gender_exact",
        )
    if text in {"nữ", "kỹ thuật viên nữ"}:
        return _entity_required(
            policy,
            state,
            required_intent="select_therapist",
            query="female",
            kind=NLUEntityKind.THERAPIST,
            confidence=1.0,
            matched_rule="therapist_gender_exact",
        )
    query = _strip_prefixes(
        text,
        ("chọn kỹ thuật viên ", "chọn chị ", "chọn anh ", "chị ", "anh "),
    )
    if query != text and query:
        return _entity_required(
            policy,
            state,
            required_intent="select_therapist",
            query=query,
            kind=NLUEntityKind.THERAPIST,
            confidence=0.8,
            matched_rule="therapist_query_state",
        )
    return None


def _strip_prefixes(text: str, prefixes: tuple[str, ...]) -> str:
    for prefix in prefixes:
        if text.startswith(prefix):
            return text[len(prefix) :].strip()
    return text


def _strip_suffixes(text: str, suffixes: tuple[str, ...]) -> str:
    for suffix in suffixes:
        if text.endswith(suffix):
            return text[: -len(suffix)].strip()
    return text


def _has_secondary_entities(
    text: str,
    today: date,
    *,
    primary: str,
) -> bool:
    found = False
    if primary != "booking_date":
        booking_date, _ = _extract_date(text, today)
        if booking_date is not None:
            found = True
    if primary != "start_time":
        start_time = _extract_time(text)
        if start_time is not None:
            found = True
    if primary != "num_customer":
        people = _extract_people(text, allow_bare=False)
        if people is not None:
            found = True
    if primary != "duration_minutes":
        duration, _ = _extract_duration(text, allow_bare=False)
        if duration is not None:
            found = True
    return found


def _validate_dispatch_payload(
    intent: str,
    payload: Mapping[str, object],
) -> None:
    if intent == "change_info":
        _validate_change_payload(payload)
        return
    expected_keys: frozenset[str]
    expected_type: type[object] | None
    if intent == "select_people":
        expected_keys, expected_type = frozenset({"num_customer"}), int
    elif intent == "select_duration":
        expected_keys, expected_type = frozenset({"duration_minutes"}), int
    elif intent == "select_date":
        expected_keys, expected_type = frozenset({"booking_date"}), date
    elif intent == "select_time":
        expected_keys, expected_type = frozenset({"start_time"}), time
    elif intent == "provide_phone":
        expected_keys, expected_type = frozenset({"phone"}), str
    elif intent == "ask_question":
        expected_keys, expected_type = frozenset({"query"}), str
    elif intent in {
        "cancel_flow",
        "confirm",
        "deny",
        "greeting",
        "ask_why",
        "list_addons",
        "list_available_times",
        "list_services",
        "list_shops",
        "list_therapists",
        "repeat_last_question",
        "restart_booking",
        "start_booking",
        "thanks",
        "unknown",
    }:
        expected_keys, expected_type = frozenset(), None
    elif intent == "search_shops":
        expected_keys, expected_type = frozenset({"location_query"}), str
    else:
        raise NLUResultNotDispatchableError(
            "NLU intent has no direct dispatch payload contract."
        )

    if frozenset(payload) != expected_keys:
        raise NLUResultNotDispatchableError(
            "NLU payload does not match the dispatch contract."
        )
    if expected_type is not None:
        value = next(iter(payload.values()))
        if expected_type is int:
            valid_type = type(value) is int
        else:
            valid_type = type(value) is expected_type
        if not valid_type:
            raise NLUResultNotDispatchableError(
                "NLU payload value has an invalid dispatch type."
            )


def _validate_change_payload(payload: Mapping[str, object]) -> None:
    target = payload.get("change_target")
    value_contracts: dict[str, tuple[str, type[object]]] = {
        "shop": ("shop", Shop),
        "date": ("booking_date", date),
        "people": ("num_customer", int),
        "duration": ("duration_minutes", int),
        "service": ("course_selection", CourseSelection),
        "time": ("start_time", time),
        "therapist": ("therapist_gender", str),
        "phone": ("phone", str),
    }
    if not isinstance(target, str) or target not in value_contracts:
        raise NLUResultNotDispatchableError(
            "Booking change target is not supported."
        )
    value_key, value_type = value_contracts[target]
    if frozenset(payload) == {"change_target"}:
        return
    if frozenset(payload) != {"change_target", value_key}:
        raise NLUResultNotDispatchableError(
            "Booking change payload does not match its target."
        )
    value = payload[value_key]
    if value_type is int:
        valid = type(value) is int
    else:
        valid = isinstance(value, value_type)
    if not valid:
        raise NLUResultNotDispatchableError(
            "Booking change value has an invalid type."
        )


def _looks_like_question(raw_text: str, normalized: str) -> bool:
    return raw_text.strip().endswith("?") or normalized.startswith(_QUESTION_PREFIXES)


def _freeze_mapping(values: Mapping[str, object]) -> Mapping[str, object]:
    return MappingProxyType({key: _freeze_value(value) for key, value in values.items()})


def _freeze_value(value: object) -> object:
    if isinstance(value, Mapping):
        return _freeze_mapping(value)
    if isinstance(value, list | tuple):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, set | frozenset):
        return frozenset(_freeze_value(item) for item in value)
    return value


class LLMNLUEntities(BaseModel):
    """Contains only primitive entity values accepted from an LLM."""

    model_config = ConfigDict(extra="forbid")

    number_of_people: StrictInt | None = Field(default=None, ge=1, le=3)
    duration_minutes: StrictInt | None = Field(default=None, ge=1)
    booking_date: StrictStr | None = None
    start_time: StrictStr | None = None
    phone: StrictStr | None = None
    confirmation: StrictBool | None = None
    therapist_gender: Literal["male", "female", "none"] | None = None
    change_target: BookingChangeTarget | None = None
    query: StrictStr | None = None


class LLMNLUOutput(BaseModel):
    """Defines the complete JSON object accepted from the LLM provider."""

    model_config = ConfigDict(extra="forbid")

    intent: StrictStr
    confidence: StrictFloat = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    entities: LLMNLUEntities = Field(default_factory=LLMNLUEntities)
    entity_kind: Literal["shop", "course", "therapist"] | None = None
    entity_query: StrictStr | None = None


_LLM_ISO_DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")
_LLM_CLOCK_PATTERN = re.compile(r"(?:[01]\d|2[0-3]):[0-5]\d")
_LLM_INTENT_ALIASES = {
    "select_shop": "select_store",
    "select_service": "select_course",
    "collect_phone": "provide_phone",
    "change_booking_field": "change_info",
}
_LLM_ENTITY_INTENTS = {
    NLUEntityKind.SHOP: "select_store",
    NLUEntityKind.COURSE: "select_course",
    NLUEntityKind.THERAPIST: "select_therapist",
}
_LLM_NO_PAYLOAD_INTENTS = frozenset(
    {
        "cancel_flow",
        "confirm",
        "deny",
        "list_addons",
        "list_available_times",
        "list_services",
        "list_shops",
        "list_therapists",
        "start_booking",
    }
)


class LLMNLUFallback:
    """Parse one unresolved message using validated structured LLM output."""

    def __init__(
        self,
        *,
        llm_gateway: LLMGateway,
        intent_policy: StateIntentPolicy,
        min_confidence: float = LLM_NLU_MIN_CONFIDENCE,
        enabled: bool = True,
    ) -> None:
        if (
            isinstance(min_confidence, bool)
            or not isinstance(min_confidence, int | float)
            or not isfinite(min_confidence)
            or not 0.0 <= min_confidence <= 1.0
        ):
            raise ValueError("LLM NLU confidence threshold must be between zero and one.")
        if type(enabled) is not bool:
            raise TypeError("LLM NLU enabled flag must be boolean.")
        self._llm_gateway = llm_gateway
        self._intent_policy = intent_policy
        self._min_confidence = float(min_confidence)
        self._enabled = enabled

    async def parse(self, *, text: str, state: BookingState) -> NLUResult:
        """Call the gateway once and return a policy-safe NLU result."""
        if not self._enabled:
            return _llm_unresolved()
        messages = _build_llm_messages(
            text=text,
            state=state,
            allowed_intents=self._intent_policy.allowed_for(state),
        )
        try:
            response = await self._llm_gateway.generate(messages)
        except (LLMGatewayError, TimeoutError):
            return _llm_unresolved()
        if response.content is None or not response.content.strip():
            return _llm_unresolved()
        try:
            output = LLMNLUOutput.model_validate_json(response.content)
        except (ValueError, json.JSONDecodeError):
            return _llm_unresolved()
        return self._to_nlu_result(output, state)

    def _to_nlu_result(
        self,
        output: LLMNLUOutput,
        state: BookingState,
    ) -> NLUResult:
        raw_intent = output.intent.strip()
        intent = _LLM_INTENT_ALIASES.get(raw_intent, raw_intent)
        if intent == "unknown" or output.confidence < self._min_confidence:
            return _llm_unresolved()

        entity_kind, entity_query = _llm_entity_reference(output)
        if entity_kind is not None:
            change_target = output.entities.change_target
            expected_intent = (
                "change_info"
                if change_target is not None
                else _LLM_ENTITY_INTENTS[entity_kind]
            )
            change_kind_matches = (
                change_target is None
                or (change_target == "shop" and entity_kind is NLUEntityKind.SHOP)
                or (
                    change_target == "service"
                    and entity_kind is NLUEntityKind.COURSE
                )
            )
            if (
                intent != expected_intent
                or not change_kind_matches
                or not self._intent_policy.is_allowed(state, expected_intent)
                or entity_query is None
                or not entity_query.strip()
            ):
                return _llm_unresolved()
            return NLUResult(
                intent=None,
                payload={},
                confidence=output.confidence,
                source=NLUSource.FALLBACK,
                resolution_status=NLUResolutionStatus.ENTITY_RESOLUTION_REQUIRED,
                matched_rule="llm_nlu_fallback",
                entity_query=entity_query.strip(),
                entity_kind=entity_kind,
                change_target=change_target,
            )

        if not self._intent_policy.is_allowed(state, intent):
            return _llm_unresolved()
        payload = _llm_direct_payload(intent, output.entities)
        if payload is None:
            return _llm_unresolved()
        return NLUResult(
            intent=intent,
            payload=payload,
            confidence=output.confidence,
            source=NLUSource.FALLBACK,
            resolution_status=NLUResolutionStatus.RESOLVED,
            matched_rule="llm_nlu_fallback",
        )


def _build_llm_messages(
    *,
    text: str,
    state: BookingState,
    allowed_intents: frozenset[str],
) -> list[LLMMessage]:
    intents = ", ".join(sorted(allowed_intents)) or "none"
    system_prompt = (
        "Classify one booking message. Return JSON only with keys intent, confidence, "
        "entities, entity_kind, entity_query. "
        f"Current state: {state.value}. Allowed intents: {intents}. "
        "Entities may only contain number_of_people, duration_minutes, booking_date "
        "(YYYY-MM-DD), start_time (HH:MM), phone, confirmation, therapist_gender, "
        "change_target, query. Use intent change_info for an in-progress booking "
        "change and ask_question for an FAQ query. Use list_shops, search_shops, "
        "list_services, list_addons, list_available_times, or list_therapists only "
        "for discovery requests; search_shops must put the location in entities.query. "
        "For shop/course/therapist return only entity_kind and entity_query; never infer "
        "IDs or return domain objects. Example: "
        '{"intent":"select_people","confidence":0.9,'
        '"entities":{"number_of_people":2},"entity_kind":null,'
        '"entity_query":null}.'
    )
    return [
        LLMMessage(role="system", content=system_prompt),
        LLMMessage(role="user", content=text),
    ]


def _llm_entity_reference(
    output: LLMNLUOutput,
) -> tuple[NLUEntityKind | None, str | None]:
    if output.entity_kind is not None:
        return NLUEntityKind(output.entity_kind), output.entity_query
    if output.intent.strip() == "select_therapist":
        gender = output.entities.therapist_gender
        if gender in {"male", "female"}:
            return NLUEntityKind.THERAPIST, gender
    return None, None


def _llm_direct_payload(
    intent: str,
    entities: LLMNLUEntities,
) -> dict[str, object] | None:
    if intent == "change_info":
        return _llm_change_payload(entities)
    if intent in _LLM_NO_PAYLOAD_INTENTS:
        return {}
    if intent == "ask_question" and entities.query is not None:
        query = entities.query.strip()
        return {"query": query} if query else None
    if intent == "search_shops" and entities.query is not None:
        query = entities.query.strip()
        return {"location_query": query} if query else None
    if intent == "select_people" and entities.number_of_people is not None:
        return {"num_customer": entities.number_of_people}
    if intent == "select_duration" and entities.duration_minutes is not None:
        return {"duration_minutes": entities.duration_minutes}
    if intent == "select_date" and entities.booking_date is not None:
        return _llm_date_payload(entities.booking_date)
    if intent == "select_time" and entities.start_time is not None:
        return _llm_time_payload(entities.start_time)
    if intent == "provide_phone" and entities.phone is not None:
        return {"phone": entities.phone}
    return None


def _llm_change_payload(
    entities: LLMNLUEntities,
) -> dict[str, object] | None:
    target = entities.change_target
    if target is None:
        return None
    payload: dict[str, object] = {"change_target": target}
    if target == "people" and entities.number_of_people is not None:
        payload["num_customer"] = entities.number_of_people
    elif target == "duration" and entities.duration_minutes is not None:
        payload["duration_minutes"] = entities.duration_minutes
    elif target == "date" and entities.booking_date is not None:
        parsed = _llm_date_payload(entities.booking_date)
        if parsed is None:
            return None
        payload.update(parsed)
    elif target == "time" and entities.start_time is not None:
        parsed = _llm_time_payload(entities.start_time)
        if parsed is None:
            return None
        payload.update(parsed)
    elif target == "therapist" and entities.therapist_gender is not None:
        payload["therapist_gender"] = entities.therapist_gender
    elif target == "phone" and entities.phone is not None:
        payload["phone"] = entities.phone
    return payload


def _llm_date_payload(value: str) -> dict[str, object] | None:
    if not _LLM_ISO_DATE_PATTERN.fullmatch(value):
        return None
    try:
        return {"booking_date": date.fromisoformat(value)}
    except ValueError:
        return None


def _llm_time_payload(value: str) -> dict[str, object] | None:
    if not _LLM_CLOCK_PATTERN.fullmatch(value):
        return None
    try:
        return {"start_time": time.fromisoformat(value)}
    except ValueError:
        return None


def _llm_unresolved() -> NLUResult:
    return _unresolved(matched_rule="llm_nlu_fallback")
