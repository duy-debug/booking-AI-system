"""Load immutable deterministic-NLU recognition data from JSON."""

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
            service_context = "service" in entry.entity_hints
            normalized = normalize_vietnamese(text, service_context=service_context)
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
    return Path(__file__).resolve().parent / "nlu" / "catalogs" / "intent_catalog.vi.json"


@lru_cache(maxsize=1)
def load_default_intent_catalog() -> IntentCatalog:
    """Load the process-wide default catalog once."""
    return IntentCatalogLoader.load(default_intent_catalog_path())


def normalize_vietnamese(text: str, *, service_context: bool = False) -> str:
    """Apply narrow deterministic normalization without fuzzy matching."""
    normalized = unicodedata.normalize("NFC", text).casefold().strip()
    normalized = _ADDON.sub("add on", normalized)
    normalized = _PUNCTUATION.sub(" ", normalized)
    normalized = _WHITESPACE.sub(" ", normalized).strip()
    if service_context:
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
    service_context = "service" in _string_tuple(
        raw["entity_hints"], f"Intent '{intent.value}' entity_hints", normalize=False
    )
    phrases = {
        field: _string_tuple(
            raw[field],
            f"Intent '{intent.value}' {field}",
            service_context=service_context,
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
    service_context: bool = False,
) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise InvalidIntentCatalogError(f"{label} must be a list.")
    result: list[str] = []
    for item in value:
        text = _required_text(item, label)
        result.append(
            normalize_vietnamese(text, service_context=service_context)
            if normalize
            else text
        )
    return tuple(result)
