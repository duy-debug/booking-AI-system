"""Choose one state-compatible intent from structured LLM candidates."""

import logging
from collections.abc import Mapping, Sequence
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictStr

from app.domain.booking_context import BookingContext
from app.domain.booking_state import BookingState
from app.infrastructure.context_store import trace_log


class IntentPolicy(Protocol):
    def is_allowed(self, state: BookingState, intent: str) -> bool: ...


class IntentCandidate(BaseModel):
    """One strictly validated intent hypothesis returned by Gemini."""

    model_config = ConfigDict(extra="forbid")

    intent: StrictStr
    confidence: StrictFloat = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    entities: dict[str, object] = Field(default_factory=dict)
    entity_kind: StrictStr | None = None
    entity_query: StrictStr | None = None


class IntentPrioritizer:
    """Prefer compatible and complete candidates before raw confidence."""

    _REQUIRED_ENTITY = {
        "select_people": "number_of_people",
        "select_duration": "duration_minutes",
        "select_date": "booking_date",
        "select_time": "start_time",
        "provide_phone": "phone",
        "ask_question": "query",
        "search_shops": "query",
    }

    def __init__(self, policy: IntentPolicy) -> None:
        self._policy = policy

    def choose(
        self,
        candidates: Sequence[IntentCandidate],
        *,
        state: BookingState,
        context: BookingContext | None = None,
    ) -> IntentCandidate | None:
        """Return the best valid candidate without mutating booking context."""
        compatible = [
            candidate
            for candidate in candidates
            if self._policy.is_allowed(state, _canonical_intent(candidate.intent))
        ]
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
            logging.INFO,
            "IntentPrioritizer",
            "intent_selected",
            current_state=state.value,
            selected_intent=_canonical_intent(selected.intent),
            selected_score=selected.confidence,
            secondary_intents=[
                _canonical_intent(item.intent) for item in compatible if item is not selected
            ],
            reason="state_compatible_and_entity_complete",
        )
        return selected


def _canonical_intent(intent: str) -> str:
    return {
        "select_shop": "select_store",
        "select_service": "select_course",
        "collect_phone": "provide_phone",
        "change_booking_field": "change_info",
    }.get(intent.strip(), intent.strip())


def _entity_complete(
    candidate: IntentCandidate,
    requirements: Mapping[str, str],
) -> int:
    intent = _canonical_intent(candidate.intent)
    if intent in {"select_store", "select_course", "select_therapist"}:
        return int(bool(candidate.entity_kind and candidate.entity_query))
    required = requirements.get(intent)
    return 1 if required is None or candidate.entities.get(required) is not None else 0


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
