"""Parse Vietnamese dialog input with local rules and Gemini fallback."""
# ruff: noqa: E402

import json
import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from app.domain.booking_state import BookingState

_WHITESPACE = re.compile(r"\s+")
_PUNCTUATION = re.compile(r'[.,!?;()\[\]{}"]')
_ADDON = re.compile(r"\badd[ -]?on\b")


class Intent(StrEnum):
    """Authoritative identifiers understood by the recognition catalog."""

    GREETING = "greeting"
    THANKS = "thanks"
    START_BOOKING = "start_booking"
    SELECT_SHOP = "select_shop"
    SELECT_DATE = "select_date"
    SELECT_PEOPLE = "select_people"
    SELECT_DURATION = "select_duration"
    SELECT_SERVICE = "select_service"
    LIST_SERVICES = "list_services"
    LIST_ADDONS = "list_addons"
    LIST_SHOPS = "list_shops"
    SEARCH_SHOPS = "search_shops"
    LIST_AVAILABLE_TIMES = "list_available_times"
    LIST_THERAPISTS = "list_therapists"
    SELECT_TIME = "select_time"
    SELECT_THERAPIST = "select_therapist"
    PROVIDE_PHONE = "provide_phone"
    PROVIDE_NAME = "provide_name"
    CONFIRM = "confirm"
    DENY = "deny"
    CHANGE_INFO = "change_info"
    ASK_WHY = "ask_why"
    REPEAT_LAST_QUESTION = "repeat_last_question"
    RESTART_BOOKING = "restart_booking"
    FAQ = "faq"
    UNKNOWN = "unknown"


class InvalidIntentCatalogError(ValueError):
    """Raised when recognition data violates the catalog contract."""


@dataclass(frozen=True, slots=True)
class IntentCatalogEntry:
    intent: Intent
    priority: int
    enabled: bool
    examples: tuple[str, ...]
    exact_phrases: tuple[str, ...]
    required_any_phrases: tuple[str, ...]
    optional_phrases: tuple[str, ...]
    excluded_phrases: tuple[str, ...]
    allowed_states: frozenset[BookingState]
    entity_hints: tuple[str, ...]
    mutates_context: bool


@dataclass(frozen=True, slots=True)
class IntentCatalog:
    entries: tuple[IntentCatalogEntry, ...]

    def match(
        self,
        text: str,
        state: BookingState | None = None,
    ) -> IntentCatalogEntry | None:
        """Return the first priority-ordered, state-safe phrase match."""
        candidates: list[tuple[IntentCatalogEntry, str]] = []
        for entry in self.entries:
            if not entry.enabled or (
                state is not None and state not in entry.allowed_states
            ):
                continue
            course_context = "service" in entry.entity_hints
            normalized = normalize_vietnamese(text, course_context=course_context)
            if any(_contains_phrase(normalized, phrase) for phrase in entry.excluded_phrases):
                continue
            candidates.append((entry, normalized))

        for entry, normalized in candidates:
            if normalized in entry.exact_phrases:
                return entry

        combination_matches: list[tuple[int, int, IntentCatalogEntry]] = []
        for order, (entry, normalized) in enumerate(candidates):
            if entry.required_any_phrases and any(
                _contains_phrase(normalized, phrase)
                for phrase in entry.required_any_phrases
            ):
                optional_hits = sum(
                    _contains_phrase(normalized, phrase)
                    for phrase in entry.optional_phrases
                )
                if "discovery" in entry.entity_hints and optional_hits == 0:
                    continue
                combination_matches.append((optional_hits, -order, entry))
        if not combination_matches:
            return None
        highest_priority = max(match[2].priority for match in combination_matches)
        same_priority = [
            match for match in combination_matches if match[2].priority == highest_priority
        ]
        return max(same_priority, key=lambda match: (match[0], match[1]))[2]


class IntentCatalogLoader:
    """Validate and load one UTF-8 JSON intent catalog."""

    @staticmethod
    def load(path: Path) -> IntentCatalog:
        try:
            raw: object = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise InvalidIntentCatalogError(f"Cannot load intent catalog: {error}") from error
        if isinstance(raw, dict) and "intent_catalog" in raw:
            raw = raw["intent_catalog"]
        if not isinstance(raw, dict) or set(raw) != {"version", "intents"}:
            raise InvalidIntentCatalogError(
                "Intent catalog root must contain exactly 'version' and 'intents'."
            )
        if raw["version"] != "1":
            raise InvalidIntentCatalogError("Intent catalog version must be '1'.")
        definitions = raw["intents"]
        if not isinstance(definitions, list):
            raise InvalidIntentCatalogError("Intent catalog 'intents' must be a list.")
        entries: list[IntentCatalogEntry] = []
        seen: set[Intent] = set()
        for index, definition in enumerate(definitions):
            entry = _parse_entry(definition, index)
            if entry.intent in seen:
                raise InvalidIntentCatalogError(
                    f"Duplicate intent '{entry.intent.value}' in intent catalog."
                )
            seen.add(entry.intent)
            entries.append(entry)
        missing = set(Intent) - seen
        if missing:
            names = ", ".join(sorted(intent.value for intent in missing))
            raise InvalidIntentCatalogError(f"Intent catalog is missing: {names}.")
        ordered = tuple(
            entry
            for _, entry in sorted(
                enumerate(entries), key=lambda item: (-item[1].priority, item[0])
            )
        )
        return IntentCatalog(ordered)


def default_intent_catalog_path() -> Path:
    return Path(__file__).resolve().parent / "booking_flow.json"


@lru_cache(maxsize=1)
def load_default_intent_catalog() -> IntentCatalog:
    """Load the process-wide default catalog once."""
    return IntentCatalogLoader.load(default_intent_catalog_path())


def normalize_vietnamese(text: str, *, course_context: bool = False) -> str:
    """Apply narrow deterministic normalization without fuzzy matching."""
    normalized = unicodedata.normalize("NFC", text).casefold().strip()
    normalized = _ADDON.sub("add on", normalized)
    normalized = _PUNCTUATION.sub(" ", normalized)
    normalized = _WHITESPACE.sub(" ", normalized).strip()
    if course_context:
        normalized = normalized.replace("lộ trình", "liệu trình")
    return normalized


def _contains_phrase(text: str, phrase: str) -> bool:
    return f" {phrase} " in f" {text} "


def _parse_entry(raw: object, index: int) -> IntentCatalogEntry:
    fields = {
        "intent",
        "priority",
        "enabled",
        "examples",
        "exact_phrases",
        "required_any_phrases",
        "optional_phrases",
        "excluded_phrases",
        "allowed_states",
        "entity_hints",
        "mutates_context",
    }
    if not isinstance(raw, dict) or set(raw) != fields:
        raise InvalidIntentCatalogError(f"Intent entry {index} has an invalid schema.")
    try:
        intent = Intent(_required_text(raw["intent"], f"Intent entry {index} intent"))
    except ValueError as error:
        raise InvalidIntentCatalogError(
            f"Intent entry {index} has unknown intent '{raw.get('intent')}'."
        ) from error
    priority = raw["priority"]
    if type(priority) is not int:
        raise InvalidIntentCatalogError(f"Intent '{intent.value}' priority must be an integer.")
    enabled = raw["enabled"]
    mutates_context = raw["mutates_context"]
    if type(enabled) is not bool or type(mutates_context) is not bool:
        raise InvalidIntentCatalogError(
            f"Intent '{intent.value}' boolean fields must be booleans."
        )
    course_context = "service" in _string_tuple(
        raw["entity_hints"], f"Intent '{intent.value}' entity_hints", normalize=False
    )
    phrases = {
        field: _string_tuple(
            raw[field],
            f"Intent '{intent.value}' {field}",
            course_context=course_context,
        )
        for field in (
            "examples",
            "exact_phrases",
            "required_any_phrases",
            "optional_phrases",
            "excluded_phrases",
        )
    }
    raw_states = _string_tuple(
        raw["allowed_states"], f"Intent '{intent.value}' allowed_states", normalize=False
    )
    try:
        states = frozenset(BookingState(value) for value in raw_states)
    except ValueError as error:
        raise InvalidIntentCatalogError(
            f"Intent '{intent.value}' contains an unknown state."
        ) from error
    if not states:
        raise InvalidIntentCatalogError(f"Intent '{intent.value}' must allow a state.")
    return IntentCatalogEntry(
        intent=intent,
        priority=priority,
        enabled=enabled,
        examples=phrases["examples"],
        exact_phrases=phrases["exact_phrases"],
        required_any_phrases=phrases["required_any_phrases"],
        optional_phrases=phrases["optional_phrases"],
        excluded_phrases=phrases["excluded_phrases"],
        allowed_states=states,
        entity_hints=_string_tuple(
            raw["entity_hints"], f"Intent '{intent.value}' entity_hints", normalize=False
        ),
        mutates_context=mutates_context,
    )


def _required_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidIntentCatalogError(f"{label} must be a non-empty string.")
    return value.strip()


def _string_tuple(
    value: object,
    label: str,
    *,
    normalize: bool = True,
    course_context: bool = False,
) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise InvalidIntentCatalogError(f"{label} must be a list.")
    result: list[str] = []
    for item in value:
        text = _required_text(item, label)
        result.append(
            normalize_vietnamese(text, course_context=course_context)
            if normalize
            else text
        )
    return tuple(result)

"""Deterministic and LLM-backed intent and entity parsing for dialog input."""

import logging
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, time, timedelta
from enum import StrEnum
from math import isfinite
from time import perf_counter
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
    ValidationError,
)

from app.dialog.dialog_controller import DialogTurnInput
from app.dialog.flow_loader import FlowDefinition
from app.dialog.intent_prioritizer import IntentCandidate, IntentPrioritizer
from app.domain.booking_context import BookingContext
from app.domain.booking_models import CourseSelection, Shop
from app.domain.booking_state import BookingState
from app.infrastructure.context_store import elapsed_ms, record_turn_metrics, trace_log
from app.infrastructure.gemini_client import (
    LLMGateway,
    LLMGatewayError,
    LLMMessage,
    LLMResponse,
)

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


class NLUProcessor:
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
            start_time = _extract_time(normalized)
            start_payload: dict[str, object] = {}
            if booking_date is not None:
                start_payload["booking_date"] = booking_date
            if start_time is not None:
                start_payload["start_time"] = start_time
            return _resolved(
                self._intent_policy,
                state,
                "start_booking",
                start_payload,
                0.95,
                "start_booking_phrase",
                has_unconsumed_entities=bool(start_payload),
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

        if state is BookingState.COLLECTING_NAME and text.strip():
            return _resolved(
                self._intent_policy,
                state,
                "provide_name",
                {"name": text.strip()},
                0.95,
                "customer_name_state",
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
    text = normalize_vietnamese(text, course_context=True)
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
    if text:
        return _entity_required(
            policy,
            state,
            required_intent="select_therapist",
            query=text,
            kind=NLUEntityKind.THERAPIST,
            confidence=0.8,
            matched_rule="therapist_name_state",
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
    if intent == "start_booking":
        if not set(payload).issubset({"booking_date", "start_time"}):
            raise NLUResultNotDispatchableError(
                "Start-booking payload contains unsupported fields."
            )
        if "booking_date" in payload and type(payload["booking_date"]) is not date:
            raise NLUResultNotDispatchableError("Booking date has an invalid type.")
        if "start_time" in payload and type(payload["start_time"]) is not time:
            raise NLUResultNotDispatchableError("Start time has an invalid type.")
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


class LLMNLUCandidatesOutput(BaseModel):
    """Function-call envelope containing alternative intent hypotheses."""

    model_config = ConfigDict(extra="forbid")

    candidates: list[IntentCandidate] = Field(min_length=1, max_length=5)


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
        self._prioritizer = IntentPrioritizer(intent_policy)

    async def parse(
        self,
        *,
        text: str,
        state: BookingState,
        context: BookingContext | None = None,
    ) -> NLUResult:
        """Call the gateway once and return a policy-safe NLU result."""
        if not self._enabled:
            return _llm_unresolved()
        started_at = perf_counter()
        messages = _build_llm_messages(
            text=text,
            state=state,
            allowed_intents=self._intent_policy.allowed_for(state),
        )
        trace_log(
            logging.getLogger(__name__),
            logging.INFO,
            "LLMNLU",
            "nlu_started",
            provider="gemini",
            current_state=state.value,
            prompt_chars=sum(len(message.content) for message in messages),
        )
        try:
            response = await self._llm_gateway.generate(messages, tools=[_INTENT_TOOL])
        except (LLMGatewayError, TimeoutError) as error:
            record_turn_metrics(nlu_duration_ms=elapsed_ms(started_at))
            trace_log(
                logging.getLogger(__name__),
                logging.WARNING,
                "LLMNLU",
                "nlu_failed",
                current_state=state.value,
                error_code="nlu_unavailable",
                exception_type=type(error).__name__,
                duration_ms=elapsed_ms(started_at),
            )
            return _llm_unresolved()
        try:
            candidates = _parse_llm_candidates(response)
        except (ValueError, json.JSONDecodeError) as error:
            record_turn_metrics(nlu_duration_ms=elapsed_ms(started_at))
            invalid_fields = (
                [
                    ".".join(str(part) for part in item["loc"])
                    for item in error.errors()
                ]
                if isinstance(error, ValidationError)
                else []
            )
            trace_log(
                logging.getLogger(__name__),
                logging.WARNING,
                "NLUSchema",
                "pydantic_validation_failed",
                exception_type=type(error).__name__,
                invalid_fields=invalid_fields,
                error_code="invalid_nlu_output",
            )
            return _llm_unresolved()
        trace_log(
            logging.getLogger(__name__),
            logging.INFO,
            "NLUSchema",
            "pydantic_validation_completed",
            status="success",
            candidate_count=len(candidates),
        )
        trace_log(
            logging.getLogger(__name__),
            logging.INFO,
            "LLMNLU",
            "nlu_completed",
            candidates=[
                {"intent": item.intent, "confidence": item.confidence}
                for item in candidates
            ],
            entity_fields=sorted(
                {
                    key
                    for item in candidates
                    for key, value in item.entities.items()
                    if value is not None
                }
            ),
            duration_ms=elapsed_ms(started_at),
        )
        record_turn_metrics(nlu_duration_ms=elapsed_ms(started_at))
        selected = self._prioritizer.choose(
            candidates,
            state=state,
            context=context,
        )
        if selected is None:
            return _llm_unresolved()
        output = LLMNLUOutput.model_validate(selected.model_dump())
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


_INTENT_TOOL: dict[str, object] = {
    "type": "function",
    "function": {
        "name": "extract_intent_candidates",
        "description": "Extract state-aware booking intents and primitive entities.",
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "required": ["candidates"],
            "properties": {
                "candidates": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 5,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["intent", "confidence", "entities"],
                        "properties": {
                            "intent": {"type": "string"},
                            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                            "entities": {"type": "object"},
                            "entity_kind": {
                                "type": ["string", "null"],
                                "enum": ["shop", "course", "therapist", None],
                            },
                            "entity_query": {"type": ["string", "null"]},
                        },
                    },
                }
            },
        },
    },
}


def _parse_llm_candidates(response: LLMResponse) -> list[IntentCandidate]:
    if response.tool_calls:
        call = response.tool_calls[0]
        if call.name != "extract_intent_candidates":
            raise ValueError("Unexpected NLU function call.")
        return LLMNLUCandidatesOutput.model_validate(call.arguments).candidates
    if response.content is None or not response.content.strip():
        raise ValueError("LLM NLU response is empty.")
    raw = json.loads(response.content)
    if isinstance(raw, dict) and "candidates" in raw:
        return LLMNLUCandidatesOutput.model_validate(raw).candidates
    legacy = LLMNLUOutput.model_validate(raw)
    return [IntentCandidate.model_validate(legacy.model_dump())]


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

"""Resolve NLU entity queries through application search use cases."""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType

from app.application.handlers.search_course_handler import SearchCourseHandler
from app.application.handlers.search_shop_handler import SearchShopHandler
from app.dialog.dialog_controller import DialogTurnInput
from app.domain.booking_context import BookingContext, CourseSelectionMode
from app.domain.booking_models import (
    AvailableTherapistRequest,
    Course,
    CourseType,
    InvalidCourseSelectionError,
    TherapistAvailabilityGateway,
    TherapistPreference,
    TherapistPreferenceType,
)
from app.domain.booking_state import BookingState

_SAFE_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
_SELECTION_KEY_PATTERN = re.compile(r"^(?:shop|course|therapist):\d+$")
_SAFE_METADATA_KEYS = frozenset(
    {"address", "duration_minutes", "price", "course_type"}
)


class EntityResolutionStatus(StrEnum):
    """Describes the outcome of one authoritative entity lookup."""

    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    NOT_FOUND = "not_found"
    UNSUPPORTED = "unsupported"
    FAILED = "failed"


class EntityResolutionError(Exception):
    """Base exception for entity-resolution contract misuse."""


class InvalidEntityResolutionRequestError(EntityResolutionError):
    """Raised when a coordinator receives an invalid NLU resolution request."""


class InvalidCandidateSelectionError(EntityResolutionError):
    """Raised when an ambiguous candidate cannot be selected safely."""


class EntityResolutionNotDispatchableError(EntityResolutionError):
    """Raised when a resolution result cannot become a dialog turn."""


@dataclass(frozen=True, slots=True)
class EntityCandidate:
    """Contains UI-safe candidate data and an opaque local selection key."""

    kind: NLUEntityKind
    display_name: str
    selection_key: str
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.kind, NLUEntityKind):
            raise TypeError("Entity candidate kind is invalid.")
        if not isinstance(self.display_name, str) or not self.display_name.strip():
            raise ValueError("Entity candidate display name must not be empty.")
        if not _SELECTION_KEY_PATTERN.fullmatch(self.selection_key):
            raise ValueError("Entity candidate selection key is invalid.")
        object.__setattr__(self, "display_name", self.display_name.strip())
        object.__setattr__(self, "metadata", _safe_candidate_metadata(self.metadata))


@dataclass(frozen=True, slots=True)
class _CandidateDispatch:
    dispatch_intent: str
    dispatch_payload: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "dispatch_payload",
            MappingProxyType(dict(self.dispatch_payload)),
        )


@dataclass(frozen=True, slots=True)
class EntityResolutionResult:
    """Contains a safe entity-resolution outcome without raw adapter data."""

    status: EntityResolutionStatus
    entity_kind: NLUEntityKind
    dispatch_intent: str | None
    dispatch_payload: Mapping[str, object]
    candidates: tuple[EntityCandidate, ...] = ()
    failure_code: str | None = None
    matched_count: int = 0
    _candidate_dispatches: Mapping[str, _CandidateDispatch] = field(
        default_factory=dict,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        if not isinstance(self.status, EntityResolutionStatus):
            raise TypeError("Entity resolution status is invalid.")
        if not isinstance(self.entity_kind, NLUEntityKind):
            raise TypeError("Entity resolution kind is invalid.")
        if type(self.matched_count) is not int or self.matched_count < 0:
            raise ValueError("Matched count must be a non-negative integer.")
        if self.failure_code is not None and not _SAFE_CODE_PATTERN.fullmatch(
            self.failure_code
        ):
            raise ValueError("Entity resolution failure code is invalid.")
        object.__setattr__(
            self,
            "dispatch_payload",
            MappingProxyType(dict(self.dispatch_payload)),
        )
        object.__setattr__(self, "candidates", tuple(self.candidates))
        object.__setattr__(
            self,
            "_candidate_dispatches",
            MappingProxyType(dict(self._candidate_dispatches)),
        )
        self._validate_status_shape()

    def _validate_status_shape(self) -> None:
        if self.status is EntityResolutionStatus.RESOLVED:
            if self.dispatch_intent is None or not self.dispatch_payload:
                raise ValueError("Resolved entity requires dispatch intent and payload.")
            if self.failure_code is not None:
                raise ValueError("Resolved entity cannot contain a failure code.")
            return
        if self.dispatch_intent is not None or self.dispatch_payload:
            raise ValueError("Non-resolved entity result cannot contain dispatch data.")
        if self.status is EntityResolutionStatus.AMBIGUOUS:
            if len(self.candidates) < 2 or self.matched_count != len(self.candidates):
                raise ValueError("Ambiguous entity result requires all matched candidates.")
            if self.failure_code is not None:
                raise ValueError("Ambiguous entity result cannot contain a failure code.")
        elif self.candidates:
            raise ValueError("Only ambiguous results may expose candidates.")
        if self.status in {
            EntityResolutionStatus.NOT_FOUND,
            EntityResolutionStatus.UNSUPPORTED,
            EntityResolutionStatus.FAILED,
        } and self.failure_code is None:
            raise ValueError("Unsuccessful entity result requires a safe failure code.")


class EntityResolutionCoordinator:
    """Coordinate safe shop, course and therapist entity resolution."""

    def __init__(
        self,
        *,
        search_shop_handler: SearchShopHandler,
        search_course_handler: SearchCourseHandler,
        booking_gateway: TherapistAvailabilityGateway | None = None,
    ) -> None:
        self._search_shop_handler = search_shop_handler
        self._search_course_handler = search_course_handler
        self._booking_gateway = booking_gateway

    async def resolve(
        self,
        *,
        nlu_result: NLUResult,
        state: BookingState,
        context: BookingContext,
    ) -> EntityResolutionResult:
        """Resolve one valid entity query without mutating dialog context."""
        kind, query, change_target = _validate_resolution_request(nlu_result, state)
        if kind is NLUEntityKind.SHOP:
            return await self._resolve_shop(query, change=change_target == "shop")
        if kind is NLUEntityKind.COURSE:
            return await self._resolve_course(
                query,
                context,
                change=change_target == "service",
            )
        return await self._resolve_therapist(query, context)

    def select_candidate(
        self,
        *,
        result: EntityResolutionResult,
        selection_key: str,
    ) -> EntityResolutionResult:
        """Resolve an existing ambiguous candidate without another lookup."""
        if result.status is not EntityResolutionStatus.AMBIGUOUS:
            raise InvalidCandidateSelectionError(
                "Candidate selection requires an ambiguous resolution result."
            )
        try:
            selected = result._candidate_dispatches[selection_key]
        except KeyError as error:
            raise InvalidCandidateSelectionError(
                "Candidate selection key does not exist in this result."
            ) from error
        return EntityResolutionResult(
            status=EntityResolutionStatus.RESOLVED,
            entity_kind=result.entity_kind,
            dispatch_intent=selected.dispatch_intent,
            dispatch_payload=selected.dispatch_payload,
            matched_count=1,
        )

    async def _resolve_shop(
        self,
        query: str,
        *,
        change: bool = False,
    ) -> EntityResolutionResult:
        try:
            shops = await self._search_shop_handler.execute(query)
        except Exception:
            return _failure(
                NLUEntityKind.SHOP,
                "shop_resolution_unavailable",
            )
        if not shops:
            return _not_found(NLUEntityKind.SHOP, "shop_not_found")
        dispatches = tuple(
            _CandidateDispatch(
                "change_info" if change else "select_store",
                (
                    {"change_target": "shop", "shop": shop}
                    if change
                    else {"shop": shop}
                ),
            )
            for shop in shops
        )
        if len(shops) == 1:
            return _resolved_result(NLUEntityKind.SHOP, dispatches[0])
        candidates = tuple(
            EntityCandidate(
                kind=NLUEntityKind.SHOP,
                display_name=shop.name,
                selection_key=f"shop:{index}",
                metadata={"address": shop.address} if shop.address else {},
            )
            for index, shop in enumerate(shops)
        )
        return _ambiguous_result(NLUEntityKind.SHOP, candidates, dispatches)

    async def _resolve_course(
        self,
        query: str,
        context: BookingContext,
        *,
        change: bool = False,
    ) -> EntityResolutionResult:
        if context.shop is None:
            return _failure(
                NLUEntityKind.COURSE,
                "shop_required_before_course_resolution",
            )
        try:
            course_type = None
            if not change:
                course_type = (
                    CourseType.ADDON
                    if context.course_selection_mode is CourseSelectionMode.ADDON
                    else CourseType.MAIN
                )
            courses = await self._search_course_handler.execute(
                context.shop.shop_id,
                query,
                course_type=course_type,
            )
        except Exception:
            return _failure(
                NLUEntityKind.COURSE,
                "course_resolution_unavailable",
            )
        if course_type is CourseType.MAIN and context.duration_minutes is not None:
            courses = [
                service
                for service in courses
                if service.course_type is CourseType.MAIN
                and service.duration_minutes == context.duration_minutes
            ]
        if not courses:
            return _not_found(NLUEntityKind.COURSE, "course_not_found")

        dispatches: list[_CandidateDispatch] = []
        for service in courses:
            selection = _build_course_selection(
                service,
                context,
                replace_existing=change,
            )
            if selection is None:
                return _unsupported(NLUEntityKind.COURSE, "main_course_required")
            dispatches.append(
                _CandidateDispatch(
                    "change_info" if change else "select_course",
                    (
                        {
                            "change_target": "service",
                            "course_selection": selection,
                        }
                        if change
                        else {"course_selection": selection}
                    ),
                )
            )
        if len(courses) == 1:
            return _resolved_result(NLUEntityKind.COURSE, dispatches[0])
        candidates = tuple(
            EntityCandidate(
                kind=NLUEntityKind.COURSE,
                display_name=service.name,
                selection_key=f"course:{index}",
                metadata={
                    "duration_minutes": service.duration_minutes,
                    "price": service.price,
                    "course_type": service.course_type.value,
                },
            )
            for index, service in enumerate(courses)
        )
        return _ambiguous_result(
            NLUEntityKind.COURSE,
            candidates,
            tuple(dispatches),
        )

    async def _resolve_therapist(
        self,
        query: str,
        context: BookingContext,
    ) -> EntityResolutionResult:
        preference_type = {
            "male": TherapistPreferenceType.MALE,
            "female": TherapistPreferenceType.FEMALE,
        }.get(query)
        if preference_type is not None:
            preference = TherapistPreference(preference_type)
            return _resolved_result(
                NLUEntityKind.THERAPIST,
                _CandidateDispatch(
                    "select_therapist",
                    {"therapist_preference": preference},
                ),
            )
        if context.num_customer != 1:
            return _unsupported(NLUEntityKind.THERAPIST, "personal_therapist_group_forbidden")
        if (
            self._booking_gateway is None
            or context.shop is None
            or context.booking_date is None
            or context.start_time is None
            or context.total_duration_minutes is None
        ):
            return _failure(NLUEntityKind.THERAPIST, "therapist_resolution_unavailable")
        end_time = (
            datetime.combine(context.booking_date, context.start_time)
            + timedelta(minutes=context.total_duration_minutes)
        ).time()
        try:
            therapists = await self._booking_gateway.search_available_therapists(
                AvailableTherapistRequest(
                    shop_id=context.shop.shop_id,
                    booking_date=context.booking_date,
                    start_time=context.start_time,
                    end_time=end_time,
                )
            )
        except Exception:
            return _failure(NLUEntityKind.THERAPIST, "therapist_resolution_unavailable")
        normalized_query = query.casefold().strip()
        matches = [
            therapist
            for therapist in therapists
            if therapist.therapist_name is not None
            and normalized_query in therapist.therapist_name.casefold()
        ]
        if not matches:
            return _not_found(NLUEntityKind.THERAPIST, "therapist_not_found")
        dispatches = tuple(
            _CandidateDispatch("select_therapist", {"therapist_preference": item})
            for item in matches
        )
        if len(matches) == 1:
            return _resolved_result(NLUEntityKind.THERAPIST, dispatches[0])
        candidates = tuple(
            EntityCandidate(
                kind=NLUEntityKind.THERAPIST,
                display_name=item.therapist_name or "Kỹ thuật viên",
                selection_key=f"therapist:{index}",
            )
            for index, item in enumerate(matches)
        )
        return _ambiguous_result(NLUEntityKind.THERAPIST, candidates, dispatches)


def entity_resolution_to_dialog_turn_input(
    result: EntityResolutionResult,
    *,
    state: BookingState,
    intent_policy: StateIntentPolicy,
    idempotency_key: str | None = None,
) -> DialogTurnInput:
    """Map only a resolved, policy-valid Domain payload to a dialog turn."""
    if (
        result.status is not EntityResolutionStatus.RESOLVED
        or result.dispatch_intent is None
    ):
        raise EntityResolutionNotDispatchableError(
            "Entity resolution result is not resolved for dispatch."
        )
    if not intent_policy.is_allowed(state, result.dispatch_intent):
        raise EntityResolutionNotDispatchableError(
            "Resolved entity intent is not allowed in the current state."
        )
    _validate_resolution_payload(result.dispatch_intent, result.dispatch_payload)
    return DialogTurnInput(
        intent=result.dispatch_intent,
        payload=result.dispatch_payload,
        idempotency_key=idempotency_key,
    )


def _validate_resolution_request(
    result: NLUResult,
    state: BookingState,
) -> tuple[NLUEntityKind, str, str | None]:
    if (
        result.resolution_status
        is not NLUResolutionStatus.ENTITY_RESOLUTION_REQUIRED
        or result.intent is not None
        or result.payload
        or result.entity_kind is None
        or result.entity_query is None
        or not result.entity_query.strip()
    ):
        raise InvalidEntityResolutionRequestError(
            "NLU result does not satisfy the entity-resolution request contract."
        )
    expected_state = {
        NLUEntityKind.SHOP: BookingState.SELECTING_SHOP,
        NLUEntityKind.COURSE: BookingState.SELECTING_SERVICE,
        NLUEntityKind.THERAPIST: BookingState.SELECTING_THERAPIST,
    }[result.entity_kind]
    if result.change_target is None and state is not expected_state:
        raise InvalidEntityResolutionRequestError(
            "Entity kind is not valid for the current dialog state."
        )
    expected_change_kind = {
        "shop": NLUEntityKind.SHOP,
        "service": NLUEntityKind.COURSE,
    }
    if (
        result.change_target is not None
        and expected_change_kind.get(result.change_target) is not result.entity_kind
    ):
        raise InvalidEntityResolutionRequestError(
            "Change target does not match the requested entity kind."
        )
    return result.entity_kind, result.entity_query, result.change_target


def _build_course_selection(
    service: Course,
    context: BookingContext,
    *,
    replace_existing: bool = False,
) -> CourseSelection | None:
    try:
        if service.course_type is CourseType.MAIN:
            return CourseSelection(
                service,
                () if replace_existing else context.addons,
            )
        if replace_existing:
            return None
        if context.main_course is None:
            return None
        return CourseSelection(
            context.main_course,
            context.addons + (service,),
        )
    except InvalidCourseSelectionError:
        return None


def _resolved_result(
    kind: NLUEntityKind,
    dispatch: _CandidateDispatch,
) -> EntityResolutionResult:
    return EntityResolutionResult(
        status=EntityResolutionStatus.RESOLVED,
        entity_kind=kind,
        dispatch_intent=dispatch.dispatch_intent,
        dispatch_payload=dispatch.dispatch_payload,
        matched_count=1,
    )


def _not_found(kind: NLUEntityKind, code: str) -> EntityResolutionResult:
    return EntityResolutionResult(
        status=EntityResolutionStatus.NOT_FOUND,
        entity_kind=kind,
        dispatch_intent=None,
        dispatch_payload={},
        failure_code=code,
    )


def _unsupported(kind: NLUEntityKind, code: str) -> EntityResolutionResult:
    return EntityResolutionResult(
        status=EntityResolutionStatus.UNSUPPORTED,
        entity_kind=kind,
        dispatch_intent=None,
        dispatch_payload={},
        failure_code=code,
    )


def _failure(kind: NLUEntityKind, code: str) -> EntityResolutionResult:
    return EntityResolutionResult(
        status=EntityResolutionStatus.FAILED,
        entity_kind=kind,
        dispatch_intent=None,
        dispatch_payload={},
        failure_code=code,
    )


def _ambiguous_result(
    kind: NLUEntityKind,
    candidates: tuple[EntityCandidate, ...],
    dispatches: tuple[_CandidateDispatch, ...],
) -> EntityResolutionResult:
    return EntityResolutionResult(
        status=EntityResolutionStatus.AMBIGUOUS,
        entity_kind=kind,
        dispatch_intent=None,
        dispatch_payload={},
        candidates=candidates,
        matched_count=len(candidates),
        _candidate_dispatches=MappingProxyType(
            {
                candidate.selection_key: dispatch
                for candidate, dispatch in zip(candidates, dispatches, strict=True)
            }
        ),
    )


def _safe_candidate_metadata(values: Mapping[str, object]) -> Mapping[str, object]:
    safe: dict[str, object] = {}
    for key, value in values.items():
        if key not in _SAFE_METADATA_KEYS:
            continue
        if key in {"address", "course_type"} and isinstance(value, str):
            safe[key] = value
        elif key == "duration_minutes" and type(value) is int and value > 0:
            safe[key] = value
        elif key == "price" and isinstance(value, Decimal):
            safe[key] = value
    return MappingProxyType(safe)


def _validate_resolution_payload(
    intent: str,
    payload: Mapping[str, object],
) -> None:
    expected: tuple[str, type[object]]
    if intent == "change_info":
        target = payload.get("change_target")
        expected_change: tuple[str, type[object]]
        if target == "shop":
            expected_change = ("shop", Shop)
        elif target == "service":
            expected_change = ("course_selection", CourseSelection)
        else:
            raise EntityResolutionNotDispatchableError(
                "Resolved change entity has an invalid target."
            )
        change_key, change_type = expected_change
        if frozenset(payload) != {"change_target", change_key} or not isinstance(
            payload[change_key], change_type
        ):
            raise EntityResolutionNotDispatchableError(
                "Resolved change entity payload is invalid."
            )
        return
    if intent == "select_store":
        expected = ("shop", Shop)
    elif intent == "select_course":
        expected = ("course_selection", CourseSelection)
    elif intent == "select_therapist":
        expected = ("therapist_preference", TherapistPreference)
    else:
        raise EntityResolutionNotDispatchableError(
            "Resolved entity intent has no dispatch contract."
        )
    key, expected_type = expected
    if frozenset(payload) != {key} or not isinstance(payload[key], expected_type):
        raise EntityResolutionNotDispatchableError(
            "Resolved entity payload does not match its dispatch contract."
        )
