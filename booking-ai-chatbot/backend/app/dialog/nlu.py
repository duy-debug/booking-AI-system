"""Parse structured Gemini dialog output and resolve booking entities."""
# ruff: noqa: E402, F811

from __future__ import annotations

import json
import logging
import re
import unicodedata
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from enum import StrEnum
from math import isfinite
from time import perf_counter
from types import MappingProxyType
from typing import TYPE_CHECKING, Literal, TypeAlias
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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

from app.dialog.flow_loader import FlowDefinition
from app.dialog.intent_prioritizer import IntentCandidate, IntentPrioritizer
from app.domain.booking_context import BookingContext
from app.domain.booking_models import CourseSelection, Shop
from app.domain.booking_state import BookingState
from app.domain.outcomes import HandlerOutcome
from app.infrastructure.context_store import elapsed_ms, record_turn_metrics, trace_log
from app.infrastructure.gemini_client import (
    LLMGateway,
    LLMGatewayError,
    LLMMessage,
    LLMResponse,
)

_WHITESPACE = re.compile(r"\s+")
_PUNCTUATION = re.compile(r'[.,!?;()\[\]{}"]')
_ADDON = re.compile(r"\badd[ -]?on\b")


def normalize_vietnamese(text: str, *, course_context: bool = False) -> str:
    """Normalize shared Vietnamese entity queries without fuzzy matching."""
    normalized = unicodedata.normalize("NFC", text).casefold().strip()
    normalized = _ADDON.sub("add on", normalized)
    normalized = _PUNCTUATION.sub(" ", normalized)
    normalized = _WHITESPACE.sub(" ", normalized).strip()
    if course_context:
        normalized = normalized.replace("lộ trình", "liệu trình")
    return normalized


if TYPE_CHECKING:
    from app.dialog.dialog_controller import DialogTurnInput

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
SUPPORTED_NLU_INTENTS = frozenset(
    {
        "ask_question",
        "ask_why",
        "cancel_flow",
        "change_info",
        "confirm",
        "deny",
        "greeting",
        "list_addons",
        "list_available_times",
        "list_services",
        "list_shops",
        "list_therapists",
        "provide_name",
        "provide_phone",
        "repeat_last_question",
        "restart_booking",
        "search_shops",
        "select_course",
        "select_date",
        "select_duration",
        "select_people",
        "select_store",
        "select_therapist",
        "select_time",
        "start_booking",
        "thanks",
        "unknown",
    }
)
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
        "list_services": frozenset(BookingState),
        "list_addons": frozenset(BookingState),
        "list_available_times": frozenset(BookingState),
        "list_therapists": frozenset(BookingState),
    }
)

_RULE_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
_WHITESPACE_PATTERN = re.compile(r"\s+")
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

_CANCEL_PHRASES = frozenset({"hủy", "hủy đặt lịch", "dừng đặt lịch", "thôi không đặt nữa"})
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
    merged_entities: Mapping[str, object] = field(default_factory=dict)

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
        if self.matched_rule is not None and not _RULE_NAME_PATTERN.fullmatch(self.matched_rule):
            raise ValueError("Matched rule must be a safe snake_case identifier.")
        if not isinstance(self.has_unconsumed_entities, bool):
            raise TypeError("Unconsumed-entity marker must be boolean.")
        self._validate_resolution_shape()
        if self.intent is not None:
            object.__setattr__(self, "intent", self.intent.strip())
        object.__setattr__(self, "confidence", float(self.confidence))
        object.__setattr__(self, "payload", _freeze_mapping(self.payload))
        object.__setattr__(
            self,
            "merged_entities",
            _freeze_mapping(self.merged_entities),
        )
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


def to_dialog_turn_input(
    result: NLUResult,
    *,
    state: BookingState,
    intent_policy: StateIntentPolicy,
    idempotency_key: str | None = None,
    raw_message: str | None = None,
) -> DialogTurnInput:
    """Map only a policy-valid and payload-safe result to a dialog turn."""
    from app.dialog.dialog_controller import DialogTurnInput

    if not result.is_dispatchable() or result.intent is None:
        raise NLUResultNotDispatchableError("NLU result is not resolved for dispatch.")
    if not intent_policy.is_allowed(state, result.intent):
        raise NLUResultNotDispatchableError("NLU intent is not allowed in the current state.")
    payload = dict(result.payload)
    if result.intent == "start_booking":
        booking_date = result.merged_entities.get("booking_date")
        start_time = result.merged_entities.get("start_time")
        if type(booking_date) is date:
            payload["booking_date"] = booking_date
        if type(start_time) is time:
            payload["start_time"] = start_time
    _validate_dispatch_payload(result.intent, payload)
    return DialogTurnInput(
        intent=result.intent,
        payload=payload,
        idempotency_key=idempotency_key,
        raw_message=raw_message,
    )


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
    elif intent == "provide_name":
        expected_keys, expected_type = frozenset({"name"}), str
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
        raise NLUResultNotDispatchableError("NLU intent has no direct dispatch payload contract.")

    if frozenset(payload) != expected_keys:
        raise NLUResultNotDispatchableError("NLU payload does not match the dispatch contract.")
    if expected_type is not None:
        value = next(iter(payload.values()))
        if expected_type is int:
            valid_type = type(value) is int
        else:
            valid_type = type(value) is expected_type
        if not valid_type:
            raise NLUResultNotDispatchableError("NLU payload value has an invalid dispatch type.")


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
        raise NLUResultNotDispatchableError("Booking change target is not supported.")
    value_key, value_type = value_contracts[target]
    if frozenset(payload) == {"change_target"}:
        return
    if frozenset(payload) != {"change_target", value_key}:
        raise NLUResultNotDispatchableError("Booking change payload does not match its target.")
    value = payload[value_key]
    if value_type is int:
        valid = type(value) is int
    else:
        valid = isinstance(value, value_type)
    if not valid:
        raise NLUResultNotDispatchableError("Booking change value has an invalid type.")


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

    number_of_people: StrictInt | None = None
    duration_minutes: StrictInt | None = Field(default=None, ge=1)
    booking_date: StrictStr | None = None
    start_time: StrictStr | None = None
    phone: StrictStr | None = None
    confirmation: StrictBool | None = None
    therapist_gender: Literal["male", "female", "none"] | None = None
    change_target: BookingChangeTarget | None = None
    query: StrictStr | None = None
    shop_name: StrictStr | None = None
    service_name: StrictStr | None = None
    main_course_name: StrictStr | None = None
    addon_name: StrictStr | None = None
    skip_addon: StrictBool | None = None
    therapist_name: StrictStr | None = None
    customer_name: StrictStr | None = None


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
        "greeting",
        "list_addons",
        "list_available_times",
        "list_services",
        "list_shops",
        "list_therapists",
        "start_booking",
        "thanks",
        "ask_why",
        "repeat_last_question",
    }
)


class LLMNLU:
    """Parse every message using validated Gemini structured output."""

    def __init__(
        self,
        *,
        llm_gateway: LLMGateway,
        intent_policy: StateIntentPolicy,
        min_confidence: float = LLM_NLU_MIN_CONFIDENCE,
        business_timezone: str = "Asia/Ho_Chi_Minh",
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        if (
            isinstance(min_confidence, bool)
            or not isinstance(min_confidence, int | float)
            or not isfinite(min_confidence)
            or not 0.0 <= min_confidence <= 1.0
        ):
            raise ValueError("LLM NLU confidence threshold must be between zero and one.")
        try:
            timezone_info = ZoneInfo(business_timezone)
        except ZoneInfoNotFoundError as error:
            raise ValueError("BUSINESS_TIMEZONE must be a valid IANA timezone.") from error
        self._llm_gateway = llm_gateway
        self._intent_policy = intent_policy
        self._min_confidence = float(min_confidence)
        self._business_timezone = business_timezone
        self._timezone_info = timezone_info
        self._now_provider = now_provider or _utc_now
        self._prioritizer = IntentPrioritizer(intent_policy)

    async def parse(
        self,
        *,
        text: str,
        state: BookingState,
        context: BookingContext | None = None,
    ) -> NLUResult:
        # Dùng LLM tool calling để nhận diện intent và trích xuất entity có cấu trúc.
        """Call the gateway once and return a policy-safe NLU result."""
        started_at = perf_counter()
        current_datetime = self._now_provider()
        if current_datetime.tzinfo is None:
            current_datetime = current_datetime.replace(tzinfo=timezone.utc)
        local_datetime = current_datetime.astimezone(self._timezone_info)
        messages = _build_llm_messages(
            text=text,
            state=state,
            allowed_intents=self._intent_policy.allowed_for(state),
            current_datetime=local_datetime,
            business_timezone=self._business_timezone,
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
            return _llm_unresolved("nlu_unavailable")
        try:
            candidates = _parse_llm_candidates(response)
        except (ValueError, json.JSONDecodeError) as error:
            record_turn_metrics(nlu_duration_ms=elapsed_ms(started_at))
            invalid_fields = (
                [".".join(str(part) for part in item["loc"]) for item in error.errors()]
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
            return _llm_unresolved("invalid_nlu_output")
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
                {"intent": item.intent, "confidence": item.confidence} for item in candidates
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
            if state in {BookingState.COMPLETED, BookingState.CANCELLED} and any(
                _LLM_INTENT_ALIASES.get(item.intent.strip(), item.intent.strip()) == "change_info"
                for item in candidates
            ):
                return _llm_unresolved("state_incompatible_change_info")
            return _llm_unresolved("invalid_nlu_output")
        merged_entities = _merge_candidate_entities(candidates)
        try:
            output = LLMNLUOutput.model_validate(selected.model_dump())
        except ValidationError as error:
            trace_log(
                logging.getLogger(__name__),
                logging.WARNING,
                "NLUSchema",
                "selected_candidate_validation_failed",
                invalid_fields=[
                    ".".join(str(part) for part in item["loc"]) for item in error.errors()
                ],
                error_code="invalid_nlu_output",
            )
            return _llm_unresolved("invalid_nlu_output")
        return self._to_nlu_result(output, state, merged_entities)

    def _to_nlu_result(
        self,
        output: LLMNLUOutput,
        state: BookingState,
        merged_entities: Mapping[str, object],
    ) -> NLUResult:
        raw_intent = output.intent.strip()
        intent = _LLM_INTENT_ALIASES.get(raw_intent, raw_intent)
        if intent == "unknown" or output.confidence < self._min_confidence:
            return _llm_unresolved("invalid_nlu_output")

        entity_kind, entity_query = _llm_entity_reference(output)
        if entity_kind is not None:
            change_target = output.entities.change_target
            expected_intent = (
                "change_info" if change_target is not None else _LLM_ENTITY_INTENTS[entity_kind]
            )
            change_kind_matches = (
                change_target is None
                or (change_target == "shop" and entity_kind is NLUEntityKind.SHOP)
                or (change_target == "service" and entity_kind is NLUEntityKind.COURSE)
            )
            if (
                intent != expected_intent
                or not change_kind_matches
                or not self._intent_policy.is_allowed(state, expected_intent)
                or entity_query is None
                or not entity_query.strip()
            ):
                return _llm_unresolved("invalid_nlu_output")
            return NLUResult(
                intent=None,
                payload={},
                confidence=output.confidence,
                source=NLUSource.FALLBACK,
                resolution_status=NLUResolutionStatus.ENTITY_RESOLUTION_REQUIRED,
                matched_rule="llm_nlu",
                entity_query=entity_query.strip(),
                entity_kind=entity_kind,
                change_target=change_target,
                has_unconsumed_entities=bool(merged_entities),
                merged_entities=merged_entities,
            )

        if not self._intent_policy.is_allowed(state, intent):
            return _llm_unresolved("invalid_nlu_output")
        payload = _llm_direct_payload(intent, output.entities)
        if payload is None:
            return _llm_unresolved("invalid_nlu_output")
        return NLUResult(
            intent=intent,
            payload=payload,
            confidence=output.confidence,
            source=NLUSource.FALLBACK,
            resolution_status=NLUResolutionStatus.RESOLVED,
            matched_rule="llm_nlu",
            has_unconsumed_entities=_has_merged_secondary_entities(
                intent,
                merged_entities,
            ),
            merged_entities=merged_entities,
        )


def _build_llm_messages(
    *,
    text: str,
    state: BookingState,
    allowed_intents: frozenset[str],
    current_datetime: datetime,
    business_timezone: str,
) -> list[LLMMessage]:
    intents = ", ".join(sorted(allowed_intents)) or "none"
    system_prompt = (
        "Classify one booking message. Return JSON only with keys intent, confidence, "
        "entities, entity_kind, entity_query. "
        f"Current state: {state.value}. Allowed intents: {intents}. "
        f"Current business date: {current_datetime.date().isoformat()}. "
        f"Current local time: {current_datetime.time().isoformat(timespec='minutes')}. "
        f"Timezone: {business_timezone}. Locale: vi-VN. "
        "Resolve hôm nay from current business date, ngày mai as +1 day, and "
        "ngày kia as +2 days. Return booking_date as YYYY-MM-DD. "
        "Extract every explicit entity, including secondary ones. Allowed entity keys: "
        "number_of_people, duration_minutes, booking_date, start_time, phone, confirmation, "
        "therapist_gender, therapist_name, customer_name, change_target, query, shop_name, "
        "service_name, main_course_name, addon_name, skip_addon. main_course_name is the "
        "primary course; addon_name is optional; service_name means type unclear. Set "
        "skip_addon=true only for an explicit decline. Use change_info for booking edits, "
        "ask_question for FAQ, and list/search intents only for discovery. search_shops "
        "stores location in query. Shop/course/therapist selections use entity_kind and "
        "entity_query; never invent IDs. Example: "
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
                            "entities": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "number_of_people": {"type": ["integer", "null"]},
                                    "duration_minutes": {"type": ["integer", "null"]},
                                    "booking_date": {"type": ["string", "null"]},
                                    "start_time": {"type": ["string", "null"]},
                                    "phone": {"type": ["string", "null"]},
                                    "confirmation": {"type": ["boolean", "null"]},
                                    "therapist_gender": {"type": ["string", "null"]},
                                    "therapist_name": {"type": ["string", "null"]},
                                    "customer_name": {"type": ["string", "null"]},
                                    "change_target": {"type": ["string", "null"]},
                                    "query": {"type": ["string", "null"]},
                                    "shop_name": {"type": ["string", "null"]},
                                    "service_name": {"type": ["string", "null"]},
                                    "main_course_name": {"type": ["string", "null"]},
                                    "addon_name": {"type": ["string", "null"]},
                                    "skip_addon": {"type": ["boolean", "null"]},
                                },
                            },
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
    # Chuyển intent đã chọn thành payload chuẩn; intent xã hội không cần entity.
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
    if intent == "provide_name" and entities.customer_name is not None:
        name = entities.customer_name.strip()
        return {"name": name} if name else None
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


def _merge_candidate_entities(
    candidates: list[IntentCandidate],
) -> dict[str, object]:
    """Merge non-conflicting, schema-approved entities across all candidates."""
    merged: dict[str, object] = {}
    conflicts: set[str] = set()
    allowed = set(LLMNLUEntities.model_fields)
    for candidate in candidates:
        for key, raw_value in candidate.entities.items():
            if key not in allowed or raw_value is None or key in conflicts:
                continue
            value = _typed_llm_entity(key, raw_value)
            if value is None:
                continue
            if key in merged and merged[key] != value:
                merged.pop(key, None)
                conflicts.add(key)
            else:
                merged[key] = value
    return merged


def _typed_llm_entity(key: str, value: object) -> object | None:
    if key == "booking_date" and isinstance(value, str):
        payload = _llm_date_payload(value)
        return payload["booking_date"] if payload is not None else None
    if key == "start_time" and isinstance(value, str):
        payload = _llm_time_payload(value)
        return payload["start_time"] if payload is not None else None
    if key in {
        "shop_name",
        "service_name",
        "main_course_name",
        "addon_name",
        "therapist_name",
        "customer_name",
        "query",
        "phone",
    }:
        return value.strip() if isinstance(value, str) and value.strip() else None
    if key in {"number_of_people", "duration_minutes"}:
        return value if type(value) is int else None
    if key in {"confirmation", "skip_addon"}:
        return value if type(value) is bool else None
    if key in {"therapist_gender", "change_target"}:
        return value if isinstance(value, str) else None
    return None


def _has_merged_secondary_entities(
    intent: str,
    merged_entities: Mapping[str, object],
) -> bool:
    primary_keys = {
        "select_people": {"number_of_people"},
        "select_duration": {"duration_minutes"},
        "select_date": {"booking_date"},
        "select_time": {"start_time"},
        "provide_phone": {"phone"},
        "ask_question": {"query"},
    }.get(intent, set())
    return bool(set(merged_entities) - primary_keys)


def _llm_unresolved(error_code: str = "invalid_nlu_output") -> NLUResult:
    return _unresolved(matched_rule=error_code)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


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
_SAFE_METADATA_KEYS = frozenset({"address", "duration_minutes", "price", "course_type"})


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
        if self.failure_code is not None and not _SAFE_CODE_PATTERN.fullmatch(self.failure_code):
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
        if (
            self.status
            in {
                EntityResolutionStatus.NOT_FOUND,
                EntityResolutionStatus.UNSUPPORTED,
                EntityResolutionStatus.FAILED,
            }
            and self.failure_code is None
        ):
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
            result = await self._search_shop_handler.execute(query)
        except Exception:
            return _failure(
                NLUEntityKind.SHOP,
                "shop_resolution_unavailable",
            )
        if result.outcome is HandlerOutcome.NOT_FOUND:
            return _not_found(NLUEntityKind.SHOP, "shop_not_found")
        shops_value = result.data.get("shops")
        if result.outcome is not HandlerOutcome.SUCCESS or not isinstance(shops_value, tuple):
            return _failure(NLUEntityKind.SHOP, "shop_resolution_unavailable")
        shops = shops_value
        dispatches = tuple(
            _CandidateDispatch(
                "change_info" if change else "select_store",
                ({"change_target": "shop", "shop": shop} if change else {"shop": shop}),
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
            result = await self._search_course_handler.execute(
                context.shop.shop_id,
                query,
                course_type=course_type,
            )
        except Exception:
            return _failure(
                NLUEntityKind.COURSE,
                "course_resolution_unavailable",
            )
        if result.outcome is HandlerOutcome.NOT_FOUND:
            return _not_found(NLUEntityKind.COURSE, "course_not_found")
        courses_value = result.data.get("courses")
        if result.outcome not in {
            HandlerOutcome.SUCCESS,
            HandlerOutcome.AMBIGUOUS,
        } or not isinstance(courses_value, tuple):
            return _failure(NLUEntityKind.COURSE, "course_resolution_unavailable")
        courses = courses_value
        if course_type is CourseType.MAIN and context.duration_minutes is not None:
            courses = tuple(
                service
                for service in courses
                if service.course_type is CourseType.MAIN
                and service.duration_minutes == context.duration_minutes
            )
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
    from app.dialog.dialog_controller import DialogTurnInput

    if result.status is not EntityResolutionStatus.RESOLVED or result.dispatch_intent is None:
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
        result.resolution_status is not NLUResolutionStatus.ENTITY_RESOLUTION_REQUIRED
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
            raise EntityResolutionNotDispatchableError("Resolved change entity payload is invalid.")
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
