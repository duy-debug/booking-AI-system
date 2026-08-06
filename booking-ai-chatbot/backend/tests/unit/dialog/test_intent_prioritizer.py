"""Intent candidate ordering must be explicit and state-aware."""

from app.dialog.intent_prioritizer import IntentCandidate, IntentPrioritizer
from app.domain.booking_context import BookingContext
from app.domain.booking_state import BookingState


class AllowListPolicy:
    def __init__(self, allowed: set[str]) -> None:
        self.allowed = allowed

    def is_allowed(self, state: BookingState, intent: str) -> bool:
        del state
        return intent in self.allowed


def candidate(
    intent: str,
    confidence: float,
    *,
    entities: dict[str, object] | None = None,
) -> IntentCandidate:
    return IntentCandidate(
        intent=intent,
        confidence=confidence,
        entities=entities or {},
    )


def test_rejects_higher_confidence_intent_not_allowed_in_current_state() -> None:
    prioritizer = IntentPrioritizer(AllowListPolicy({"select_people"}))

    selected = prioritizer.choose(
        [
            candidate("start_booking", 0.99),
            candidate("select_people", 0.75, entities={"number_of_people": 2}),
        ],
        state=BookingState.SELECTING_PEOPLE,
    )

    assert selected is not None
    assert selected.intent == "select_people"


def test_complete_candidate_beats_higher_confidence_incomplete_candidate() -> None:
    prioritizer = IntentPrioritizer(AllowListPolicy({"select_people"}))

    selected = prioritizer.choose(
        [
            candidate("select_people", 0.99),
            candidate("select_people", 0.72, entities={"number_of_people": 3}),
        ],
        state=BookingState.SELECTING_PEOPLE,
        context=BookingContext(conversation_id="priority-test"),
    )

    assert selected is not None
    assert selected.entities == {"number_of_people": 3}


def test_returns_none_when_no_candidate_is_state_compatible() -> None:
    prioritizer = IntentPrioritizer(AllowListPolicy({"select_time"}))

    selected = prioritizer.choose(
        [candidate("select_date", 0.95)],
        state=BookingState.SELECTING_TIME,
    )

    assert selected is None
