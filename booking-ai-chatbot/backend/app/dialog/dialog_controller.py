"""Orchestrate one parsed dialog turn across workflow primitives."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from app.dialog.flow_loader import (
    ChangeRule,
    FlowAutoTransition,
    FlowDefinition,
    FlowFailure,
    FlowOnEnter,
    FlowTransition,
)
from app.dialog.state_machine import StateMachine
from app.dialog.tool_bridge import (
    ActionExecutionContext,
    ActionExecutionError,
    ActionExecutionReport,
    ToolBridge,
    ToolBridgeError,
)
from app.domain.booking_context import BookingContext
from app.domain.booking_state import BookingState


class DialogControllerError(Exception):
    """Base exception for dialog orchestration errors."""


class InvalidDialogTurnError(DialogControllerError):
    """Raised when a parsed dialog turn violates the input contract."""


class AutoTransitionLimitError(DialogControllerError):
    """Raised when one turn exceeds its auto-transition limit."""


class AutoTransitionCycleError(DialogControllerError):
    """Raised when an auto-transition signature repeats in one turn."""


@dataclass(frozen=True, slots=True)
class DialogTurnInput:
    """Contains an already parsed intent and its typed payload."""

    intent: str
    payload: Mapping[str, object]
    idempotency_key: str | None = None
    raw_message: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.intent, str) or not self.intent.strip():
            raise InvalidDialogTurnError("Dialog intent must be a non-empty string.")
        if not isinstance(self.payload, Mapping):
            raise InvalidDialogTurnError("Dialog payload must be a mapping.")
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))


class DialogTurnStatus(StrEnum):
    """Describes whether a parsed dialog turn completed or recovered."""

    SUCCESS = "success"
    FAILURE_HANDLED = "failure_handled"
    FAILURE_UNHANDLED = "failure_unhandled"


@dataclass(frozen=True, slots=True)
class DialogTurnResult:
    """Contains orchestration metadata without rendering a response."""

    status: DialogTurnStatus
    initial_state: BookingState
    final_state: BookingState
    intent: str
    instruction_template: str | None
    executed_actions: tuple[str, ...]
    auto_transition_count: int
    failure_code: str | None = None
    failed_action: str | None = None
    original_error: ActionExecutionError | None = None


class DialogController:
    """Coordinates state resolution, action execution and state commits."""

    def __init__(
        self,
        *,
        flow: FlowDefinition,
        state_machine: StateMachine,
        tool_bridge: ToolBridge,
        change_rules: Mapping[str, ChangeRule] | None = None,
        max_auto_transitions: int = 8,
    ) -> None:
        if type(max_auto_transitions) is not int or max_auto_transitions < 1:
            raise ValueError("max_auto_transitions must be at least one.")
        self._flow = flow
        self._state_machine = state_machine
        self._tool_bridge = tool_bridge
        self._change_rules = dict(change_rules or {})
        self._max_auto_transitions = max_auto_transitions

    async def handle_turn(
        self,
        booking_context: BookingContext,
        turn: DialogTurnInput,
    ) -> DialogTurnResult:
        """Execute one already parsed dialog turn without rendering output."""
        initial_state = booking_context.state
        action_context = ActionExecutionContext(
            booking_context=booking_context,
            intent=turn.intent,
            payload=turn.payload,
            idempotency_key=turn.idempotency_key,
        )
        change_rule: ChangeRule | None = None
        has_change_value = False
        if turn.intent == "change_info":
            change_rule, transition, has_change_value = self._change_transition(
                booking_context,
                turn,
            )
        else:
            transition = self._state_machine.resolve_transition(
                booking_context,
                turn.intent,
            )

        try:
            transition_report = await self._execute_actions(
                transition.actions,
                action_context,
            )
        except ActionExecutionError as error:
            return await self._recover_failure(
                source=transition,
                error=error,
                booking_context=booking_context,
                action_context=action_context,
                initial_state=initial_state,
                intent=turn.intent,
                committed_actions=(),
                auto_transition_count=0,
            )

        committed_actions = transition_report.executed_action_names
        self._state_machine.apply_transition(booking_context, transition)
        on_enter = self._flow.states[booking_context.state].on_enter
        try:
            on_enter_report = await self._execute_state_on_enter(
                booking_context,
                booking_context.state,
                action_context,
            )
        except ActionExecutionError as error:
            return await self._recover_failure(
                source=on_enter,
                error=error,
                booking_context=booking_context,
                action_context=action_context,
                initial_state=initial_state,
                intent=turn.intent,
                committed_actions=committed_actions,
                auto_transition_count=0,
            )

        committed_actions += on_enter_report.executed_action_names
        if change_rule is not None:
            return self._success_result(
                booking_context=booking_context,
                initial_state=initial_state,
                intent=turn.intent,
                instruction_template=(
                    on_enter.instruction_template
                    if has_change_value
                    else change_rule.prompt_template
                ),
                committed_actions=committed_actions,
                auto_transition_count=0,
            )
        return await self._execute_auto_transitions(
            booking_context=booking_context,
            action_context=action_context,
            initial_state=initial_state,
            intent=turn.intent,
            committed_actions=committed_actions,
            instruction_template=on_enter.instruction_template,
        )

    def _change_transition(
        self,
        booking_context: BookingContext,
        turn: DialogTurnInput,
    ) -> tuple[ChangeRule, FlowTransition, bool]:
        target = turn.payload.get("change_target")
        if not isinstance(target, str):
            raise InvalidDialogTurnError(
                "A booking change requires a supported change target."
            )
        try:
            rule = self._change_rules[target]
        except KeyError as error:
            raise InvalidDialogTurnError(
                "The requested booking field cannot be changed."
            ) from error
        self._state_machine.resolve_transition(booking_context, turn.intent)
        has_value = len(turn.payload) > 1
        transition = FlowTransition(
            intent=turn.intent,
            target=rule.applied_state if has_value else rule.next_state,
            actions=(rule.reset_action,),
            on_fail=(
                FlowFailure(
                    condition="*",
                    target=booking_context.state,
                    instruction_template="change_invalid",
                ),
            ),
        )
        return rule, transition, has_value

    async def _execute_auto_transitions(
        self,
        *,
        booking_context: BookingContext,
        action_context: ActionExecutionContext,
        initial_state: BookingState,
        intent: str,
        committed_actions: tuple[str, ...],
        instruction_template: str | None,
    ) -> DialogTurnResult:
        count = 0
        seen: set[tuple[BookingState, BookingState, tuple[str, ...]]] = set()
        while True:
            auto_transition = self._state_machine.resolve_auto_transition(
                booking_context
            )
            if auto_transition is None:
                return self._success_result(
                    booking_context=booking_context,
                    initial_state=initial_state,
                    intent=intent,
                    instruction_template=instruction_template,
                    committed_actions=committed_actions,
                    auto_transition_count=count,
                )

            try:
                self._guard_auto_transition(
                    source_state=booking_context.state,
                    transition=auto_transition,
                    count=count,
                    seen=seen,
                )
            except AutoTransitionLimitError:
                return self._guard_failure_result(
                    booking_context=booking_context,
                    initial_state=initial_state,
                    intent=intent,
                    committed_actions=committed_actions,
                    auto_transition_count=count,
                    failure_code="auto_transition_limit_exceeded",
                )
            except AutoTransitionCycleError:
                return self._guard_failure_result(
                    booking_context=booking_context,
                    initial_state=initial_state,
                    intent=intent,
                    committed_actions=committed_actions,
                    auto_transition_count=count,
                    failure_code="auto_transition_cycle_detected",
                )

            try:
                auto_report = await self._execute_actions(
                    auto_transition.actions,
                    action_context,
                )
            except ActionExecutionError as error:
                return await self._recover_failure(
                    source=auto_transition,
                    error=error,
                    booking_context=booking_context,
                    action_context=action_context,
                    initial_state=initial_state,
                    intent=intent,
                    committed_actions=committed_actions,
                    auto_transition_count=count,
                )

            committed_actions += auto_report.executed_action_names
            self._state_machine.apply_transition(booking_context, auto_transition)
            count += 1
            on_enter = self._flow.states[booking_context.state].on_enter
            try:
                on_enter_report = await self._execute_state_on_enter(
                    booking_context,
                    booking_context.state,
                    action_context,
                )
            except ActionExecutionError as error:
                return await self._recover_failure(
                    source=on_enter,
                    error=error,
                    booking_context=booking_context,
                    action_context=action_context,
                    initial_state=initial_state,
                    intent=intent,
                    committed_actions=committed_actions,
                    auto_transition_count=count,
                )

            committed_actions += on_enter_report.executed_action_names
            if on_enter.instruction_template is not None:
                instruction_template = on_enter.instruction_template

    async def _recover_failure(
        self,
        *,
        source: FlowTransition | FlowAutoTransition | FlowOnEnter,
        error: ActionExecutionError,
        booking_context: BookingContext,
        action_context: ActionExecutionContext,
        initial_state: BookingState,
        intent: str,
        committed_actions: tuple[str, ...],
        auto_transition_count: int,
    ) -> DialogTurnResult:
        failure_code = self._tool_bridge.get_failure_code(error)
        failure = self._state_machine.resolve_failure(source, failure_code)
        if failure is None:
            return self._unhandled_failure_result(
                booking_context=booking_context,
                initial_state=initial_state,
                intent=intent,
                committed_actions=committed_actions,
                auto_transition_count=auto_transition_count,
                failure_code=failure_code,
                failed_action=error.action_name,
                original_error=error,
            )

        try:
            failure_report = await self._execute_failure_actions(
                failure,
                action_context,
            )
        except ActionExecutionError as recovery_error:
            return self._unhandled_failure_result(
                booking_context=booking_context,
                initial_state=initial_state,
                intent=intent,
                committed_actions=committed_actions,
                auto_transition_count=auto_transition_count,
                failure_code=failure_code,
                failed_action=recovery_error.action_name,
                original_error=error,
            )

        self._state_machine.apply_failure(booking_context, failure)
        booking_context.last_failure_code = failure_code
        return DialogTurnResult(
            status=DialogTurnStatus.FAILURE_HANDLED,
            initial_state=initial_state,
            final_state=booking_context.state,
            intent=intent,
            instruction_template=failure.instruction_template,
            executed_actions=(
                committed_actions + failure_report.executed_action_names
            ),
            auto_transition_count=auto_transition_count,
            failure_code=failure_code,
            failed_action=error.action_name,
            original_error=error,
        )

    async def _execute_state_on_enter(
        self,
        booking_context: BookingContext,
        state: BookingState,
        action_context: ActionExecutionContext,
    ) -> ActionExecutionReport:
        on_enter = self._flow.states[state].on_enter
        report = await self._execute_actions(on_enter.actions, action_context)
        assert booking_context.state is state
        return report

    async def _execute_actions(
        self,
        action_names: Sequence[str],
        action_context: ActionExecutionContext,
    ) -> ActionExecutionReport:
        try:
            return await self._tool_bridge.execute_actions(
                action_names,
                action_context,
            )
        except ActionExecutionError:
            raise
        except ToolBridgeError as error:
            action_name = self._error_action_name(action_names)
            raise ActionExecutionError(action_name, (), error) from error

    async def _execute_failure_actions(
        self,
        failure: FlowFailure,
        action_context: ActionExecutionContext,
    ) -> ActionExecutionReport:
        try:
            return await self._tool_bridge.execute_failure_actions(
                failure,
                action_context,
            )
        except ActionExecutionError:
            raise
        except ToolBridgeError as error:
            action_name = self._error_action_name(failure.actions)
            raise ActionExecutionError(action_name, (), error) from error

    def _guard_auto_transition(
        self,
        *,
        source_state: BookingState,
        transition: FlowAutoTransition,
        count: int,
        seen: set[tuple[BookingState, BookingState, tuple[str, ...]]],
    ) -> None:
        if count >= self._max_auto_transitions:
            raise AutoTransitionLimitError(
                "Maximum auto transitions exceeded for one turn."
            )
        signature = (source_state, transition.target, transition.actions)
        if signature in seen:
            raise AutoTransitionCycleError(
                "An auto-transition signature repeated in one turn."
            )
        seen.add(signature)

    @staticmethod
    def _error_action_name(action_names: Sequence[str]) -> str:
        return action_names[-1] if action_names else "action_sequence"

    @staticmethod
    def _success_result(
        *,
        booking_context: BookingContext,
        initial_state: BookingState,
        intent: str,
        instruction_template: str | None,
        committed_actions: tuple[str, ...],
        auto_transition_count: int,
    ) -> DialogTurnResult:
        return DialogTurnResult(
            status=DialogTurnStatus.SUCCESS,
            initial_state=initial_state,
            final_state=booking_context.state,
            intent=intent,
            instruction_template=instruction_template,
            executed_actions=committed_actions,
            auto_transition_count=auto_transition_count,
        )

    @staticmethod
    def _guard_failure_result(
        *,
        booking_context: BookingContext,
        initial_state: BookingState,
        intent: str,
        committed_actions: tuple[str, ...],
        auto_transition_count: int,
        failure_code: str,
    ) -> DialogTurnResult:
        return DialogTurnResult(
            status=DialogTurnStatus.FAILURE_UNHANDLED,
            initial_state=initial_state,
            final_state=booking_context.state,
            intent=intent,
            instruction_template=None,
            executed_actions=committed_actions,
            auto_transition_count=auto_transition_count,
            failure_code=failure_code,
        )

    @staticmethod
    def _unhandled_failure_result(
        *,
        booking_context: BookingContext,
        initial_state: BookingState,
        intent: str,
        committed_actions: tuple[str, ...],
        auto_transition_count: int,
        failure_code: str,
        failed_action: str,
        original_error: ActionExecutionError,
    ) -> DialogTurnResult:
        return DialogTurnResult(
            status=DialogTurnStatus.FAILURE_UNHANDLED,
            initial_state=initial_state,
            final_state=booking_context.state,
            intent=intent,
            instruction_template=None,
            executed_actions=committed_actions,
            auto_transition_count=auto_transition_count,
            failure_code=failure_code,
            failed_action=failed_action,
            original_error=original_error,
        )
