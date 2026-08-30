"""Chọn intent phù hợp nhất từ các candidate structured mà LLM trả về."""

import logging
from collections.abc import Mapping, Sequence
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictStr

from app.domain.booking_context import BookingContext
from app.domain.booking_state import BookingState
from app.infrastructure.context_store import trace_log


class IntentPolicy(Protocol):
    """Contract tối thiểu để kiểm tra một intent có hợp lệ với state hay không."""

    def is_allowed(self, state: BookingState, intent: str) -> bool: ...


class IntentCandidate(BaseModel):
    """Một giả thuyết intent đã được validate shape từ output của Gemini."""

    model_config = ConfigDict(extra="forbid")

    intent: StrictStr
    confidence: StrictFloat = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    entities: dict[str, object] = Field(default_factory=dict)
    entity_kind: StrictStr | None = None
    entity_query: StrictStr | None = None


class IntentPrioritizer:
    """
    Chọn candidate cuối cùng để đưa sang dialog flow.

    Lớp này thuộc tầng NLU hậu xử lý: nó không đọc raw text mà chỉ so sánh
    các candidate đã có structured output, ưu tiên intent hợp state và đủ entity
    cần thiết trước khi nhìn vào confidence thuần.
    """

    _REQUIRED_ENTITY = {
        "select_people": "number_of_people",
        "select_duration": "duration_minutes",
        "select_date": "booking_date",
        "select_time": "start_time",
        "provide_phone": "phone",
        "provide_name": "customer_name",
        "ask_question": "query",
        "search_shops": "query",
    }

    # Nhận policy state để không chọn intent mà flow hiện tại không cho phép.
    def __init__(self, policy: IntentPolicy) -> None:
        self._policy = policy

    # Chọn intent phù hợp nhất dựa trên confidence, state hiện tại và độ đầy đủ entity.
    def choose(
        self,
        candidates: Sequence[IntentCandidate],
        *,
        state: BookingState,
        context: BookingContext | None = None,
    ) -> IntentCandidate | None:
        """Trả về candidate tốt nhất mà không làm thay đổi `BookingContext`."""
        compatible: list[IntentCandidate] = []
        for candidate in candidates:
            canonical_intent = _canonical_intent(
                candidate.intent,
                candidate,
                state,
            )
            is_compatible = self._policy.is_allowed(state, canonical_intent)
            if not is_compatible:
                trace_log(
                    logging.getLogger(__name__),
                    logging.INFO,
                    "IntentPrioritizer",
                    "candidate_rejected",
                    candidate_intent=canonical_intent,
                    confidence=candidate.confidence,
                    current_state=state.value,
                    compatible=False,
                    rejection_reason="state_incompatible",
                )
                continue
            compatible.append(candidate)
        if not compatible:
            trace_log(
                logging.getLogger(__name__),
                logging.WARNING,
                "IntentPrioritizer",
                "intent_selection_failed",
                current_state=state.value,
                candidate_count=len(candidates),
                reason="no_state_compatible_candidate",
            )
            return None
        selected = max(
            compatible,
            key=lambda candidate: (
                _entity_complete(candidate, self._REQUIRED_ENTITY),
                _context_compatible(candidate, context),
                candidate.confidence,
            ),
        )
        trace_log(
            logging.getLogger(__name__),
            logging.DEBUG,
            "[3] NLU",
            "intent_selected",
            current_state=state.value,
            selected_intent=_canonical_intent(selected.intent, selected, state),
            selected_score=selected.confidence,
            secondary_intents=[
                _canonical_intent(item.intent, item, state)
                for item in compatible
                if item is not selected
            ],
            reason="state_compatible_and_entity_complete",
        )
        return selected


# Chuẩn hóa alias intent từ LLM về tên intent canonical mà backend sử dụng.
def _canonical_intent(
    intent: str,
    candidate: IntentCandidate | None = None,
    state: BookingState | None = None,
) -> str:
    normalized = {
        "select_service": "select_course",
        "select_addon": "select_course",
        "collect_phone": "provide_phone",
        "change_booking_field": "change_info",
        "skip_addon": "deny",
    }.get(intent.strip(), intent.strip())
    if candidate is None:
        return normalized
    if candidate.entities.get("skip_addon") is True and normalized in {
        "select_course",
        "list_addons",
        "list_services",
    }:
        return "deny"
    if (
        state is BookingState.SELECTING_SERVICE
        and normalized in {"list_addons", "list_services"}
        and _has_course_query(candidate)
    ):
        return "select_course"
    return normalized


def _has_course_query(candidate: IntentCandidate) -> bool:
    return any(
        isinstance(value := candidate.entities.get(key), str) and value.strip()
        for key in ("service_name", "main_course_name", "addon_name")
    )


# Chấm candidate có đủ entity bắt buộc cho intent hiện tại hay chưa.
def _entity_complete(
    candidate: IntentCandidate,
    requirements: Mapping[str, str],
) -> int:
    intent = _canonical_intent(candidate.intent)
    if intent in {"select_store", "select_therapist"}:
        return int(bool(candidate.entity_kind and candidate.entity_query))
    if intent == "select_course":
        if candidate.entity_kind and candidate.entity_query:
            return 1
        return int(
            any(
                isinstance(value := candidate.entities.get(key), str) and value.strip()
                for key in ("service_name", "main_course_name", "addon_name")
            )
        )
    required = requirements.get(intent)
    return 1 if required is None or candidate.entities.get(required) is not None else 0


# Ưu tiên candidate phù hợp với dữ liệu context đã có, ví dụ slot/time hoặc shop/course.
def _context_compatible(
    candidate: IntentCandidate,
    context: BookingContext | None,
) -> int:
    if context is None:
        return 1
    intent = _canonical_intent(candidate.intent)
    if intent == "select_time":
        return int(context.available_slots is not None)
    if intent == "select_course":
        return int(context.shop is not None)
    return 1
