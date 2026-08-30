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


# Chuẩn hóa tiếng Việt dùng chung cho tìm kiếm entity mà không fuzzy match quá rộng.
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
    "main_course",
    "service",
    "addon",
    "time",
    "therapist",
    "phone",
    "customer_name",
]

LLM_NLU_MIN_CONFIDENCE = 0.70
SUPPORTED_NLU_INTENTS = frozenset(
    {
        "ask_question",
        "ask_why",
        "cancel_existing_booking",
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
class NLUSource(StrEnum):
    """Identifies the structured source of a parsed NLU result."""

    LLM = "llm"
    CONTEXT = "context"


class NLUResolutionStatus(StrEnum):
    """Describes whether an NLU result is safe to dispatch."""

    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"
    ENTITY_RESOLUTION_REQUIRED = "entity_resolution_required"


class NLUEntityKind(StrEnum):
    """Đánh dấu loại entity cần được resolver authoritative xử lý tiếp."""

    SHOP = "shop"
    COURSE = "course"
    THERAPIST = "therapist"


class NLUResultNotDispatchableError(Exception):
    """Phát sinh khi kết quả NLU chưa đủ an toàn để dispatch vào dialog flow."""


@dataclass(frozen=True, slots=True)
class StateIntentPolicy:
    """Giữ policy bất biến về intent hợp lệ theo từng state của flow."""

    allowed_intents: Mapping[BookingState, frozenset[str]]
    wildcard_states: frozenset[BookingState]

    # Đóng băng policy để runtime không thể vô tình sửa allowed intents giữa các lượt chat.
    # Validate candidate hiển thị để không lộ metadata nhạy cảm hoặc key không an toàn.
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

    # Trả danh sách intent được phép ở một state, đã cộng thêm wildcard global nếu có.
    def allowed_for(self, state: BookingState) -> frozenset[str]:
        """Return named intents accepted by one state."""
        return self.allowed_intents.get(state, frozenset())

    # Kiểm tra intent có được phép xử lý tại state hiện tại hay không.
    def is_allowed(self, state: BookingState, intent: str) -> bool:
        """Return whether an exact named intent is accepted by one state."""
        return intent in self.allowed_for(state)

    # Kiểm tra state có fallback wildcard cho unknown/recovery hay không.
    def has_wildcard(self, state: BookingState) -> bool:
        """Return whether a state declares a separate wildcard transition."""
        return state in self.wildcard_states


# Tạo policy intent từ flow JSON để LLM NLU không route ngoài state machine.
def build_state_intent_policy(
    flow: FlowDefinition,
    *,
    enable_faq: bool = False,
    enable_discovery: bool = False,
) -> StateIntentPolicy:
    """Tạo policy intent từ flow JSON để NLU không route ra ngoài state machine."""
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
    """Kết quả NLU canonical dùng cho các bước điều phối phía sau."""

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

    # Validate NLUResult để chỉ result hợp lệ mới đi tiếp sang controller.
    # Validate kết quả resolution để chỉ status hợp lệ mới có payload dispatch.
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

    # Cho biết result đã đủ intent/payload để dispatch thẳng vào DialogController hay chưa.
    def is_dispatchable(self) -> bool:
        """Return whether the result has the basic shape required for dispatch."""
        return (
            self.resolution_status is NLUResolutionStatus.RESOLVED
            and self.intent is not None
            and self.entity_query is None
            and self.entity_kind is None
        )

    # Đảm bảo status resolved/entity/unresolved có shape đúng và không lẫn trách nhiệm.
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
            if self.change_target not in {None, "shop", "main_course", "service", "addon"}:
                raise ValueError("Entity resolution change target is invalid.")
        elif (
            self.entity_query is not None
            or self.entity_kind is not None
            or self.change_target is not None
        ):
            raise ValueError("Unresolved NLU result cannot contain an entity query.")


# Chuyển NLUResult đã resolved thành DialogTurnInput canonical cho DialogController.
def to_dialog_turn_input(
    result: NLUResult,
    *,
    state: BookingState,
    intent_policy: StateIntentPolicy,
    idempotency_key: str | None = None,
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
    )


# Tạo NLUResult recovery khi LLM/provider không trả output đáp ứng contract.
def _unresolved(
    *,
    confidence: float = 0.0,
    source: NLUSource = NLUSource.LLM,
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


# Kiểm tra payload nghiệp vụ tối thiểu tương ứng từng intent trước khi dispatch.
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
    elif intent == "cancel_existing_booking":
        expected_keys, expected_type = frozenset({"phone", "booking_reference"}), str
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

    if intent == "cancel_existing_booking":
        if not set(payload).issubset(expected_keys):
            raise NLUResultNotDispatchableError("NLU payload does not match the dispatch contract.")
        if any(type(value) is not str for value in payload.values()):
            raise NLUResultNotDispatchableError("NLU payload value has an invalid dispatch type.")
        return

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


# Validate change payload để chỉnh sửa booking luôn có target và value đúng kiểu.
def _validate_change_payload(payload: Mapping[str, object]) -> None:
    if not payload:
        return
    target = payload.get("change_target")
    value_contracts: dict[str, tuple[str, type[object]]] = {
        "shop": ("shop", Shop),
        "date": ("booking_date", date),
        "people": ("num_customer", int),
        "duration": ("duration_minutes", int),
        "main_course": ("course_selection", CourseSelection),
        "service": ("course_selection", CourseSelection),
        "addon": ("course_selection", CourseSelection),
        "time": ("start_time", time),
        "therapist": ("therapist_gender", str),
        "phone": ("phone", str),
        "customer_name": ("name", str),
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


# Đóng băng payload để caller sau không mutate dữ liệu NLU đã validate.
def _freeze_mapping(values: Mapping[str, object]) -> Mapping[str, object]:
    return MappingProxyType({key: _freeze_value(value) for key, value in values.items()})


# Đệ quy đóng băng list/dict trong payload thành tuple/mapping bất biến.
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
    booking_reference: StrictStr | None = None
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
_LLM_CLOCK_PATTERN = re.compile(r"(?:\d|[01]\d|2[0-3]):[0-5]\d")
_LLM_INTENT_ALIASES = {
    "select_service": "select_course",
    "select_addon": "select_course",
    "collect_phone": "provide_phone",
    "change_booking_field": "change_info",
    "skip_addon": "deny",
}
_LLM_ENTITY_INTENTS = {
    NLUEntityKind.SHOP: "select_store",
    NLUEntityKind.COURSE: "select_course",
    NLUEntityKind.THERAPIST: "select_therapist",
}
_LLM_DIRECT_PAYLOAD_INTENTS_WITHOUT_RESOLVER = frozenset(
    {
        "cancel_existing_booking",
    }
)
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
    """
    Phân tích câu người dùng bằng LLM NLU và trả về structured semantics.

    Đây là nơi duy nhất hiểu raw user text. State chỉ được dùng như ngữ cảnh hội
    thoại để hỗ trợ phân tích, không tự quyết định intent thay cho LLM.
    """

    # Nhận LLM gateway, policy state và prioritizer để biến text thành NLUResult canonical.
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

    # Gửi câu người dùng sang Gemini, validate structured output và chọn intent tốt nhất.
    async def parse(
        self,
        *,
        text: str,
        state: BookingState,
        context: BookingContext | None = None,
    ) -> NLUResult:
        # Dùng LLM tool calling để nhận diện intent và trích xuất entity có cấu trúc.
        """Gọi LLM một lần, validate output và trả về NLUResult an toàn cho flow."""
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
            logging.DEBUG,
            "[3] NLU",
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
            # Parse tool/function response hoặc JSON content thành IntentCandidate đã validate.
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
        record_turn_metrics(nlu_duration_ms=elapsed_ms(started_at))
        # Chỉ chọn candidate tương thích với state hiện tại và đủ entity bắt buộc.
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
            output = LLMNLUOutput.model_validate(
                _normalize_llm_output_payload(selected.model_dump())
            )
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
        trace_log(
            logging.getLogger(__name__),
            logging.INFO,
            "[3] NLU",
            "nlu_completed",
            intent=output.intent,
            confidence=output.confidence,
            entities={
                key: value
                for key, value in output.entities.model_dump().items()
                if value is not None
            },
            entity_kind=output.entity_kind or "none",
            entity_query=output.entity_query or "none",
            duration_ms=elapsed_ms(started_at),
        )
        # Candidate đã chọn được map thành NLUResult để DialogController xử lý tiếp.
        return self._to_nlu_result(output, state, merged_entities)

    # Chuyển IntentCandidate đã được chọn thành NLUResult canonical cho pipeline phía sau.
    def _to_nlu_result(
        self,
        output: LLMNLUOutput,
        state: BookingState,
        merged_entities: Mapping[str, object],
    ) -> NLUResult:
        raw_intent = output.intent.strip()
        intent = _LLM_INTENT_ALIASES.get(raw_intent, raw_intent)
        if output.entities.skip_addon is True and intent in {
            "select_course",
            "list_addons",
            "list_services",
        }:
            # LLM đã hiểu đúng ý nghĩa "bỏ qua add-on", nhưng đôi khi trả intent
            # discovery/list thay vì intent flow. Canonicalize về deny để dùng đúng
            # transition skip_addon có sẵn trong booking_flow.json.
            intent = "deny"
        if (
            state is BookingState.SELECTING_SERVICE
            and intent in {"list_addons", "list_services"}
            and _course_query_from_entities(output) is not None
        ):
            # Ở bước chọn course/add-on, nếu LLM đã trích xuất tên dịch vụ cụ thể
            # thì đây là thao tác chọn course, không phải yêu cầu liệt kê discovery.
            intent = "select_course"
        if (
            state is BookingState.SELECTING_THERAPIST
            and intent == "change_info"
            and output.entities.change_target in {None, "customer_name"}
            and _non_empty_text(output.entities.customer_name) is not None
        ):
            # Ở bước chọn kỹ thuật viên, tên người mà LLM đặt nhầm vào customer_name
            # vẫn là entity cần resolver theo danh sách therapist thật của POS.
            # Không route sang change_info nếu khách chưa yêu cầu đổi thông tin.
            return NLUResult(
                intent=None,
                payload={},
                confidence=output.confidence,
                source=NLUSource.LLM,
                resolution_status=NLUResolutionStatus.ENTITY_RESOLUTION_REQUIRED,
                matched_rule="llm_nlu",
                entity_query=_non_empty_text(output.entities.customer_name),
                entity_kind=NLUEntityKind.THERAPIST,
                has_unconsumed_entities=bool(merged_entities),
                merged_entities=merged_entities,
            )
        if intent == "unknown" or output.confidence < self._min_confidence:
            # Chặn candidate dưới ngưỡng trước khi đi vào flow để log rõ lý do unresolved.
            trace_log(
                logging.getLogger(__name__),
                logging.INFO,
                "LLMNLU",
                "selected_candidate_rejected",
                raw_intent=raw_intent,
                canonical_intent=intent,
                confidence=output.confidence,
                current_state=state.value,
                rejection_reason=(
                    "below_confidence_threshold"
                    if output.confidence < self._min_confidence
                    else "unknown_intent"
                ),
            )
            return _llm_unresolved("invalid_nlu_output")

        entity_kind, entity_query = _llm_entity_reference(output, intent)
        if entity_kind is not None:
            change_target = output.entities.change_target
            expected_intent = (
                "change_info" if change_target is not None else _LLM_ENTITY_INTENTS[entity_kind]
            )
            change_kind_matches = (
                change_target is None
                or (change_target == "shop" and entity_kind is NLUEntityKind.SHOP)
                or (change_target == "main_course" and entity_kind is NLUEntityKind.COURSE)
                or (change_target == "service" and entity_kind is NLUEntityKind.COURSE)
                or (change_target == "addon" and entity_kind is NLUEntityKind.COURSE)
            )
            if (
                intent != expected_intent
                or not change_kind_matches
                or not self._intent_policy.is_allowed(state, expected_intent)
                or entity_query is None
                or not entity_query.strip()
            ):
                # Ghi rõ contract nào làm candidate đã chọn bị loại trước khi vào resolver.
                trace_log(
                    logging.getLogger(__name__),
                    logging.INFO,
                    "LLMNLU",
                    "selected_candidate_rejected",
                    raw_intent=raw_intent,
                    canonical_intent=intent,
                    confidence=output.confidence,
                    current_state=state.value,
                    compatible=self._intent_policy.is_allowed(state, expected_intent),
                    rejection_reason="entity_resolution_contract_mismatch",
                )
                return _llm_unresolved("invalid_nlu_output")
            return NLUResult(
                intent=None,
                payload={},
                confidence=output.confidence,
                source=NLUSource.LLM,
                resolution_status=NLUResolutionStatus.ENTITY_RESOLUTION_REQUIRED,
                matched_rule="llm_nlu",
                entity_query=entity_query.strip(),
                entity_kind=entity_kind,
                change_target=change_target,
                has_unconsumed_entities=bool(merged_entities),
                merged_entities=merged_entities,
            )

        if not self._intent_policy.is_allowed(state, intent):
            trace_log(
                logging.getLogger(__name__),
                logging.INFO,
                "LLMNLU",
                "selected_candidate_rejected",
                raw_intent=raw_intent,
                canonical_intent=intent,
                confidence=output.confidence,
                current_state=state.value,
                compatible=False,
                rejection_reason="state_incompatible_after_canonicalization",
            )
            return _llm_unresolved("invalid_nlu_output")
        payload = _llm_direct_payload(intent, output.entities)
        if payload is None:
            trace_log(
                logging.getLogger(__name__),
                logging.INFO,
                "LLMNLU",
                "selected_candidate_rejected",
                raw_intent=raw_intent,
                canonical_intent=intent,
                confidence=output.confidence,
                current_state=state.value,
                compatible=True,
                rejection_reason="direct_payload_contract_mismatch",
            )
            return _llm_unresolved("invalid_nlu_output")
        return NLUResult(
            intent=intent,
            payload=payload,
            confidence=output.confidence,
            source=NLUSource.LLM,
            resolution_status=NLUResolutionStatus.RESOLVED,
            matched_rule="llm_nlu",
            has_unconsumed_entities=_has_merged_secondary_entities(
                intent,
                merged_entities,
            ),
            merged_entities=merged_entities,
        )


# Tạo prompt ngắn cho LLM NLU, chỉ đưa state/rule cần thiết và không đưa toàn bộ context nhạy cảm.
def _build_llm_messages(
    *,
    text: str,
    state: BookingState,
    allowed_intents: frozenset[str],
    current_datetime: datetime,
    business_timezone: str,
) -> list[LLMMessage]:
    intents = ", ".join(sorted(allowed_intents)) or "none"
    therapist_state_rule = (
        "Ở selecting_therapist, tên người/Nam/Nữ/Không yêu cầu/Bỏ qua là select_therapist; "
        "tên người phải dùng entity_kind=therapist, entity_query=tên đó, không dùng customer_name "
        "trừ khi người dùng nói rõ đổi tên khách hàng. "
        if state is BookingState.SELECTING_THERAPIST
        else ""
    )
    system_prompt = (
        "Hãy phân loại một tin nhắn đặt lịch. Chỉ trả về JSON với các khóa intent, "
        "confidence, entities, entity_kind, entity_query. "
        f"Trạng thái hiện tại: {state.value}. Các intent được phép: {intents}. "
        "Hãy xem trạng thái hiện tại chỉ như ngữ cảnh hội thoại; nó không được lấn át ý định "
        "ngữ nghĩa mà người dùng diễn đạt. "
        f"Ngày nghiệp vụ hiện tại: {current_datetime.date().isoformat()}. "
        f"Giờ địa phương hiện tại: {current_datetime.time().isoformat(timespec='minutes')}. "
        f"Múi giờ: {business_timezone}. Ngôn ngữ: vi-VN. "
        "Hiểu hôm nay theo ngày nghiệp vụ hiện tại, ngày mai là +1 ngày, và "
        "ngày kia là +2 ngày. Trả về booking_date theo định dạng YYYY-MM-DD. "
        "Trích xuất entity được nói rõ. Entity key được phép: "
        "number_of_people, duration_minutes, booking_date, start_time, phone, "
        "booking_reference, confirmation, "
        "therapist_gender, therapist_name, customer_name, change_target, query, shop_name, "
        "service_name, main_course_name, addon_name, skip_addon. main_course_name là "
        "liệu trình chính; addon_name là tùy chọn; service_name nghĩa là chưa rõ loại. Chỉ đặt "
        "skip_addon=true khi người dùng từ chối add-on rõ ràng. Dùng change_info cho "
        "Ở selecting_service khi đã có main course, câu bỏ qua/không chọn add-on "
        "=> intent=skip_addon, skip_addon=true. "
        "yêu cầu chỉnh sửa booking draft hiện tại, ask_question cho FAQ, và các intent list/search "
        "FAQ: entity_query=query=câu hỏi. "
        "chỉ cho discovery. search_shops lưu vị trí trong query. Việc chọn "
        "shop/course/therapist phải dùng entity_kind và entity_query; tuyệt đối không tự tạo ID. "
        f"{therapist_state_rule}"
        "Khi người dùng nói giờ bắt đầu cụ thể, dùng select_time và trích xuất start_time. "
        "Hiểu giờ tự nhiên/viết tắt theo ngữ cảnh, không bịa giờ còn thiếu. "
        "Với change_info, suy ra "
        "change_target từ khái niệm ngữ nghĩa mà người dùng muốn sửa, chỉ dùng các giá trị: "
        "shop, date, people, duration, main_course, addon, time, therapist, phone, customer_name. "
        "Nếu người dùng muốn "
        "chỉnh sửa booking draft hiện tại nhưng chưa nêu rõ trường nào, hãy dùng "
        "intent=change_info với change_target là null. Không được đoán target. change_info có "
        "nghĩa là chỉnh sửa booking draft hiện tại ở các draft state mà flow cho phép. "
        "Sửa/dời/hủy booking đã tạo không được gộp vào change_info. "
        "Muốn hủy booking đã tạo: intent=cancel_existing_booking, trích xuất phone và "
        "booking_reference nếu có. Ví dụ: "
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
        "description": (
            "Trích xuất intent đặt lịch theo ngữ cảnh state và các entity nguyên thủy. Xem "
            "state như ngữ cảnh hội thoại, không phải quy tắc lấn át ý nghĩa của câu người "
            "dùng. Hãy hiểu thời gian theo ngữ nghĩa trước, rồi mới chuẩn hóa giờ đặt lịch "
            "cụ thể sang HH:MM theo định dạng 24 giờ. Với các yêu cầu sửa booking draft, "
            "hãy đặt change_target thành một trong các giá trị shop, date, people, duration, "
            "main_course, addon, time, therapist, phone, customer_name; chỉ để null khi người dùng "
            "muốn sửa booking draft hiện tại nhưng chưa nói rõ trường nào. "
            "Không được gộp các yêu cầu "
            "liên quan đến booking đã được tạo trước đó vào change_info."
        ),
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
                                    "start_time": {
                                        "type": ["string", "null"],
                                        "description": (
                                            "Giờ đặt lịch được nói rõ, đã chuẩn hóa sang "
                                            "HH:MM theo định dạng 24 giờ, ví dụ 10:00 hoặc 19:00."
                                        ),
                                    },
                                    "phone": {"type": ["string", "null"]},
                                    "booking_reference": {"type": ["string", "null"]},
                                    "confirmation": {"type": ["boolean", "null"]},
                                    "therapist_gender": {"type": ["string", "null"]},
                                    "therapist_name": {"type": ["string", "null"]},
                                    "customer_name": {"type": ["string", "null"]},
                                    "change_target": {
                                        "type": ["string", "null"],
                                        "enum": [
                                            "shop",
                                            "date",
                                            "people",
                                            "duration",
                                            "main_course",
                                            "service",
                                            "addon",
                                            "time",
                                            "therapist",
                                            "phone",
                                            "customer_name",
                                            None,
                                        ],
                                        "description": (
                                            "Trường booking mà người dùng muốn chỉnh sửa. "
                                            "Chỉ để null cho yêu cầu sửa chung chung mà "
                                            "chưa nêu rõ trường."
                                        ),
                                    },
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
                            "entity_query": {
                                "type": ["string", "null"],
                                "description": (
                                    "Với ask_question, bắt buộc chứa nguyên câu hỏi của người dùng "
                                    "để FAQ/RAG dùng làm query. Với chọn shop/course/therapist, "
                                    "chứa tên entity cần resolver xử lý."
                                ),
                            },
                        },
                    },
                }
            },
        },
    },
}


# Parse structured/tool response của Gemini thành danh sách IntentCandidate hợp lệ.
def _parse_llm_candidates(response: LLMResponse) -> list[IntentCandidate]:
    """
    Runtime mới ưu tiên tool/function calling candidates.
    """
    if response.tool_calls:
        call = response.tool_calls[0]
        if call.name != "extract_intent_candidates":
            raise ValueError("Unexpected NLU function call.")
        return LLMNLUCandidatesOutput.model_validate(
            _normalize_llm_candidates_payload(
                call.arguments
            )
        ).candidates
    if response.content is None or not response.content.strip():
        raise ValueError("LLM NLU response is empty.")
    raw = json.loads(response.content)
    if isinstance(raw, dict) and "candidates" in raw:
        return LLMNLUCandidatesOutput.model_validate(
            _normalize_llm_candidates_payload(
                raw
            )
        ).candidates
    legacy = LLMNLUOutput.model_validate(_normalize_llm_output_payload(raw))
    return [IntentCandidate.model_validate(legacy.model_dump())]


# Chuyển entity reference từ LLM thành yêu cầu resolver, không tự tạo domain object.
def _llm_entity_reference(
    output: LLMNLUOutput,
    canonical_intent: str,
) -> tuple[NLUEntityKind | None, str | None]:
    if output.entity_kind is not None:
        entity_kind = NLUEntityKind(output.entity_kind)
        entity_query = output.entity_query
        if entity_kind is NLUEntityKind.THERAPIST:
            entity_query = _normalize_therapist_query(entity_query)
        return entity_kind, entity_query
    if canonical_intent == "select_store":
        shop_query = _non_empty_text(output.entities.shop_name)
        if shop_query is not None:
            return NLUEntityKind.SHOP, shop_query
    if canonical_intent == "select_course":
        course_query = _course_query_from_entities(output)
        if course_query is not None:
            return NLUEntityKind.COURSE, course_query
    if canonical_intent == "select_therapist":
        therapist_name = _non_empty_text(output.entities.therapist_name)
        if therapist_name is not None:
            return NLUEntityKind.THERAPIST, therapist_name
        gender = _normalize_therapist_gender(output.entities.therapist_gender)
        if gender is not None:
            return NLUEntityKind.THERAPIST, gender
    return None, None


def _course_query_from_entities(output: LLMNLUOutput) -> str | None:
    return (
        _non_empty_text(output.entities.main_course_name)
        or _non_empty_text(output.entities.service_name)
        or _non_empty_text(output.entities.addon_name)
    )


# Map entity từ LLM thành payload nghiệp vụ tương ứng với từng intent.
def _llm_direct_payload(
    intent: str,
    entities: LLMNLUEntities,
) -> dict[str, object] | None:
    # `{}` nghĩa là intent hợp lệ nhưng không cần payload nghiệp vụ.
    # `None` nghĩa là intent/entity không map được và sẽ bị chuyển thành unresolved.
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
    if intent == "cancel_existing_booking":
        payload: dict[str, object] = {}
        if entities.phone is not None:
            payload["phone"] = entities.phone
        if entities.booking_reference is not None:
            reference = entities.booking_reference.strip()
            if reference:
                payload["booking_reference"] = reference
        return payload
    if intent == "provide_name" and entities.customer_name is not None:
        name = entities.customer_name.strip()
        return {"name": name} if name else None
    return None

# Map change target/value từ LLM thành payload chỉnh sửa booking an toàn.
def _llm_change_payload(
    entities: LLMNLUEntities,
) -> dict[str, object] | None:
    target = entities.change_target
    if target is None:
        return {}
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
    elif target == "customer_name" and entities.customer_name is not None:
        payload["name"] = entities.customer_name
    return payload



# Parse ngày ISO từ LLM thành date chuẩn, trả None nếu provider gửi sai format.
def _llm_date_payload(value: str) -> dict[str, object] | None:
    if not _LLM_ISO_DATE_PATTERN.fullmatch(value):
        return None
    try:
        return {"booking_date": date.fromisoformat(value)}
    except ValueError:
        return None


# Parse giờ HH:MM từ LLM thành time chuẩn, trả None nếu provider gửi sai format.
def _llm_time_payload(value: str) -> dict[str, object] | None:
    if not _LLM_CLOCK_PATTERN.fullmatch(value):
        return None
    try:
        hour, minute = value.split(":", 1)
        normalized = f"{int(hour):02d}:{minute}"
        return {"start_time": time.fromisoformat(normalized)}
    except ValueError:
        return None



# Gom entity từ các candidate phụ để controller có thể tiêu thụ field đã nói sớm.
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


# Ép kiểu entity primitive từ LLM, giữ None cho giá trị không an toàn hoặc sai kiểu.
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
        "booking_reference",
    }:
        return value.strip() if isinstance(value, str) and value.strip() else None
    if key in {"number_of_people", "duration_minutes"}:
        return value if type(value) is int else None
    if key in {"confirmation", "skip_addon"}:
        return value if type(value) is bool else None
    if key == "therapist_gender":
        return _normalize_therapist_gender(value)
    if key == "change_target":
        return value if isinstance(value, str) else None
    return None


def _normalize_llm_candidates_payload(
    payload: Mapping[str, object],
) -> dict[str, object]:
    """
    Chuẩn hóa danh sách candidate trước khi validate schema nghiêm ngặt.
    """

    # ----------------------------------------------------
    # 1. Copy payload gốc
    # ----------------------------------------------------

    normalized = dict(
        payload
    )

    candidates = normalized.get(
        "candidates"
    )

    if not isinstance(candidates, list):
        return normalized


    # ----------------------------------------------------
    # 2. Normalize từng candidate
    # ----------------------------------------------------
    #
    # LLM đôi khi trả confidence là số nguyên:
    #
    # confidence: 1
    #
    # Trong khi schema nội bộ dùng StrictFloat để tránh payload
    # không rõ kiểu. Vì vậy ta chỉ ép int an toàn thành float
    # tại boundary NLU, trước khi Pydantic validate.
    # ----------------------------------------------------

    normalized["candidates"] = [
        _normalize_llm_output_payload(candidate)
        if isinstance(candidate, Mapping)
        else candidate
        for candidate in candidates
    ]

    return normalized


# Chuẩn hóa các giá trị therapist đặc thù trước khi ép vào schema nghiêm ngặt của LLM output.
def _normalize_llm_output_payload(payload: Mapping[str, object]) -> dict[str, object]:
    normalized = dict(payload)

    # ----------------------------------------------------
    # 1. Normalize confidence
    # ----------------------------------------------------
    #
    # LLM có thể trả 1 thay vì 1.0.
    # Đây vẫn là confidence hợp lệ về mặt ngữ nghĩa,
    # nên ta chuyển int thành float trước khi validate.
    # ----------------------------------------------------

    confidence = normalized.get(
        "confidence"
    )

    if type(confidence) is int:
        normalized["confidence"] = float(
            confidence
        )


    # ----------------------------------------------------
    # 2. Normalize entities
    # ----------------------------------------------------

    entities_raw = normalized.get("entities")
    if isinstance(entities_raw, Mapping):
        entities = dict(entities_raw)
        therapist_gender = _normalize_therapist_gender(entities.get("therapist_gender"))
        if therapist_gender is not None:
            entities["therapist_gender"] = therapist_gender
        therapist_name = _non_empty_text(entities.get("therapist_name"))
        if therapist_name is not None:
            entities["therapist_name"] = therapist_name

        # ------------------------------------------------
        # Đồng bộ query FAQ
        # ------------------------------------------------
        #
        # Với ask_question, RAG cần query text để retrieve.
        #
        # Contract mới yêu cầu LLM đặt:
        #
        # - entity_query:
        #     nguyên câu hỏi người dùng
        #
        # - entities.query:
        #     cùng nội dung để direct payload map thành {"query": ...}
        #
        # Đoạn này chỉ đồng bộ hai field LLM đã trả,
        # không tự quyết định intent thay LLM.
        # ------------------------------------------------

        canonical_intent = _LLM_INTENT_ALIASES.get(
            str(normalized.get("intent", "")).strip(),
            str(normalized.get("intent", "")).strip(),
        )

        if canonical_intent == "ask_question":
            question_query = (
                _non_empty_text(
                    normalized.get("entity_query")
                )
                or _non_empty_text(
                    entities.get("query")
                )
            )

            if question_query is not None:
                normalized["entity_query"] = question_query
                entities["query"] = question_query

        # ------------------------------------------------
        # Đồng bộ entity resolver bị nhiễu từ LLM
        # ------------------------------------------------
        #
        # Một số intent không dùng entity resolver. Ví dụ:
        #
        # - start_booking đi theo flow đặt lịch, không search shop
        #   nếu LLM chưa có entity_query rõ ràng.
        #
        # - cancel_existing_booking dùng direct payload
        #   phone/booking_reference, không resolve shop/course/therapist.
        #
        # Vì vậy nếu LLM hiểu đúng intent nhưng gắn nhầm:
        #
        # entity_kind: "shop"
        # entity_query: None
        #
        # thì đây là field resolver rỗng, không phải căn cứ để reject
        # intent đã được LLM chọn. Đoạn này chỉ bỏ nhiễu contract,
        # không tự suy đoán intent từ raw user text.
        # ------------------------------------------------

        if (
            (
                canonical_intent == "start_booking"
                or canonical_intent in _LLM_DIRECT_PAYLOAD_INTENTS_WITHOUT_RESOLVER
            )
            and normalized.get("entity_kind") is not None
            and _non_empty_text(normalized.get("entity_query")) is None
        ):
            normalized["entity_kind"] = None

        normalized["entities"] = entities


    # ----------------------------------------------------
    # 3. Normalize entity query đặc thù
    # ----------------------------------------------------

    if normalized.get("entity_kind") == NLUEntityKind.THERAPIST.value:
        therapist_query = _normalize_therapist_query(normalized.get("entity_query"))
        if therapist_query is not None:
            normalized["entity_query"] = therapist_query
    return normalized


# Normalize therapist query tại boundary NLU để downstream chỉ nhận canonical values an toàn.
def _normalize_therapist_query(value: object) -> str | None:
    gender = _normalize_therapist_gender(value)
    if gender is not None:
        return gender
    return _non_empty_text(value)


# Chỉ chuẩn hóa các biến thể therapist gender/none nhỏ đã được chứng minh ở runtime.
def _normalize_therapist_gender(value: object) -> str | None:
    text = _non_empty_text(value)
    if text is None:
        return None
    normalized = normalize_vietnamese(text)
    return {
        "male": "male",
        "female": "female",
        "none": "none",
        "nam": "male",
        "nu": "female",
        "nữ": "female",
        "khong yeu cau": "none",
        "không yêu cầu": "none",
    }.get(normalized)


def _non_empty_text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


# Đánh dấu người dùng đã nói thêm field ngoài intent chính để controller xử lý tiếp.
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


# Chuyển lỗi output LLM thành unresolved an toàn thay vì dispatch payload sai.
def _llm_unresolved(error_code: str = "invalid_nlu_output") -> NLUResult:
    return _unresolved(matched_rule=error_code)


# Lấy thời điểm UTC để ghi metadata request ổn định cho NLUResult.
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

    # Đóng băng dispatch candidate để lựa chọn lại không gọi POS lần nữa.
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

    # Đảm bảo mỗi status resolution có đúng shape dữ liệu và failure code phù hợp.
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
    """
    Resolve entity query từ NLU sang domain payload hoặc candidate ambiguity an toàn.

    Coordinator này chỉ chạy khi NLU chưa thể dispatch trực tiếp vì còn cần
    tra cứu authoritative như shop, course hoặc therapist.
    """

    # Nhận các search handler thật để resolve tên shop/course/therapist qua nguồn nghiệp vụ.
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

    # Resolve entity query từ NLU thành domain payload hoặc candidate ambiguity an toàn.
    async def resolve(
        self,
        *,
        nlu_result: NLUResult,
        state: BookingState,
        context: BookingContext,
    ) -> EntityResolutionResult:
        """Resolve một entity query hợp lệ mà không làm thay đổi `BookingContext`."""
        kind, query, change_target = _validate_resolution_request(nlu_result, state)
        if kind is NLUEntityKind.SHOP:
            return await self._resolve_shop(query, change=change_target == "shop")
        if kind is NLUEntityKind.COURSE:
            return await self._resolve_course(
                query,
                context,
                change_target=change_target,
            )
        return await self._resolve_therapist(query, context)

    # Chọn candidate đã resolve trước đó mà không gọi lại handler/POS.
    def select_candidate(
        self,
        *,
        result: EntityResolutionResult,
        selection_key: str,
    ) -> EntityResolutionResult:
        """Chọn lại một candidate ambiguous đã có mà không phải gọi POS/handler lần nữa."""
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

    # Tìm shop qua handler và map 0/1/n kết quả thành not_found/resolved/ambiguous.
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

    # Tìm liệu trình/add-on trong phạm vi shop hiện tại và tạo CourseSelection phù hợp.
    async def _resolve_course(
        self,
        query: str,
        context: BookingContext,
        *,
        change_target: str | None = None,
    ) -> EntityResolutionResult:
        if context.shop is None:
            return _failure(
                NLUEntityKind.COURSE,
                "shop_required_before_course_resolution",
            )
        try:
            course_type = None
            if change_target in {"main_course", "service"}:
                course_type = CourseType.MAIN
            elif change_target == "addon":
                course_type = CourseType.ADDON
            else:
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
                replace_existing=change_target in {"main_course", "service"},
            )
            if selection is None:
                return _unsupported(NLUEntityKind.COURSE, "main_course_required")
            dispatches.append(
                _CandidateDispatch(
                    "change_info" if change_target is not None else "select_course",
                    (
                        {
                            "change_target": change_target,
                            "course_selection": selection,
                        }
                        if change_target is not None
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

    # Resolve yêu cầu therapist theo giới tính hoặc tên, tôn trọng chính sách nhóm/single booking.
    async def _resolve_therapist(
        self,
        query: str,
        context: BookingContext,
    ) -> EntityResolutionResult:
        preference_type = {
            "male": TherapistPreferenceType.MALE,
            "female": TherapistPreferenceType.FEMALE,
            "none": TherapistPreferenceType.NONE,
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


# Chuyển entity resolution đã resolved thành DialogTurnInput để chạy tiếp StateMachine.
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


# Validate state/entity trước khi gọi resolver để không lookup sai loại hoặc sai state.
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
        "main_course": NLUEntityKind.COURSE,
        "service": NLUEntityKind.COURSE,
        "addon": NLUEntityKind.COURSE,
    }
    if (
        result.change_target is not None
        and expected_change_kind.get(result.change_target) is not result.entity_kind
    ):
        raise InvalidEntityResolutionRequestError(
            "Change target does not match the requested entity kind."
        )
    return result.entity_kind, result.entity_query, result.change_target


# Ghép main course và add-on theo mode hiện tại của BookingContext.
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


# Tạo EntityResolutionResult thành công từ dispatch đã được validate.
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


# Tạo kết quả không tìm thấy để renderer trả hướng dẫn nhập lại.
def _not_found(kind: NLUEntityKind, code: str) -> EntityResolutionResult:
    return EntityResolutionResult(
        status=EntityResolutionStatus.NOT_FOUND,
        entity_kind=kind,
        dispatch_intent=None,
        dispatch_payload={},
        failure_code=code,
    )


# Tạo kết quả unsupported khi loại entity không thể resolve ở trạng thái hiện tại.
def _unsupported(kind: NLUEntityKind, code: str) -> EntityResolutionResult:
    return EntityResolutionResult(
        status=EntityResolutionStatus.UNSUPPORTED,
        entity_kind=kind,
        dispatch_intent=None,
        dispatch_payload={},
        failure_code=code,
    )


# Tạo failure an toàn khi handler/POS lỗi hoặc response không đúng contract.
def _failure(kind: NLUEntityKind, code: str) -> EntityResolutionResult:
    return EntityResolutionResult(
        status=EntityResolutionStatus.FAILED,
        entity_kind=kind,
        dispatch_intent=None,
        dispatch_payload={},
        failure_code=code,
    )


# Tạo danh sách candidate hiển thị khi có nhiều kết quả cùng phù hợp.
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


# Lọc metadata candidate để không lộ UUID/raw payload ra response.
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


# Kiểm tra payload domain sau resolution trước khi chuyển sang DialogTurnInput.
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
        elif target in {"main_course", "service", "addon"}:
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
