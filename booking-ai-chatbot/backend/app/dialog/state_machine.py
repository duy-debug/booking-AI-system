"""Resolve declarative booking conversation transitions."""

from app.dialog.flow_loader import (
    FlowAutoTransition,
    FlowDefinition,
    FlowState,
    FlowTransition,
    PhoneSplitConfig,
)
from app.domain.booking_context import BookingContext
from app.domain.booking_state import BookingState
from app.domain.exceptions import InvalidBookingStateError


class StateMachine:
    """Resolves flow transitions without executing their declarative behavior."""

    def __init__(self, flow: FlowDefinition) -> None:
        self._flow = flow

    def resolve_transition(
        self,
        current_state: BookingState,
        intent: str,
    ) -> FlowTransition:
        """Resolve the first exact transition, then a wildcard fallback."""
        transitions = self.get_state_definition(current_state).transitions
        for transition in transitions:
            if transition.intent == intent:
                return transition
        for transition in transitions:
            if transition.intent == "*":
                return transition
        raise InvalidBookingStateError(
            f"Cannot transition from '{current_state.value}' using intent '{intent}'."
        )

    def can_transition(
        self,
        current_state: BookingState,
        intent: str,
    ) -> bool:
        """Return whether an exact or wildcard transition is available."""
        transitions = self.get_state_definition(current_state).transitions
        return any(item.intent in {intent, "*"} for item in transitions)

    def transition(
        self,
        context: BookingContext,
        intent: str,
    ) -> FlowTransition:
        """Apply only the target state and return the resolved transition."""
        resolved = self.resolve_transition(context.state, intent)
        context.state = resolved.target
        return resolved

    def available_events(
        self,
        current_state: BookingState,
    ) -> tuple[str, ...]:
        """Return configured intents in insertion order."""
        return tuple(
            transition.intent
            for transition in self.get_state_definition(current_state).transitions
        )

    def get_state_definition(self, state: BookingState) -> FlowState:
        """Return the flow definition for a booking state."""
        try:
            return self._flow.states[state]
        except KeyError as exc:
            raise InvalidBookingStateError(
                f"State '{state.value}' is not declared in the flow."
            ) from exc

    def get_auto_transitions(
        self,
        state: BookingState,
    ) -> tuple[FlowAutoTransition, ...]:
        """Return parsed auto transitions without evaluating them."""
        return self.get_state_definition(state).auto_transitions

    def get_phone_split_config(
        self,
        state: BookingState,
    ) -> PhoneSplitConfig | None:
        """Return phone split configuration without executing phone logic."""
        return self.get_state_definition(state).phone_split_mode
