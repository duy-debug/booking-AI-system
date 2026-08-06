"""Load and validate declarative booking dialog flow definitions."""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from app.domain.booking_state import BookingState

SUPPORTED_OPERATORS = frozenset({"eq", "not_null", "null", "gte", "lte", "in", "and", "or"})
_ACTION_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
_FORBIDDEN_FAILURE_ACTIONS = frozenset({"create_booking"})


@dataclass(frozen=True, slots=True)
class FlowCondition:
    """Represents a parsed condition that is not evaluated by the loader."""

    field: str | None = None
    op: str = ""
    value: object | None = None
    ref: str | None = None
    conditions: tuple["FlowCondition", ...] = ()


@dataclass(frozen=True, slots=True)
class FlowFailure:
    """Defines a declarative failure route."""

    condition: str
    target: BookingState
    actions: tuple[str, ...] = ()
    instruction_template: str | None = None


@dataclass(frozen=True, slots=True)
class FlowTransition:
    """Defines an intent-driven transition to another booking state."""

    intent: str
    target: BookingState
    actions: tuple[str, ...] = ()
    conditions: tuple[FlowCondition, ...] = ()
    on_fail: tuple[FlowFailure, ...] = ()


@dataclass(frozen=True, slots=True)
class FlowAutoTransition:
    """Defines a condition-driven transition for future evaluation."""

    condition: FlowCondition
    target: BookingState
    actions: tuple[str, ...] = ()
    on_fail: tuple[FlowFailure, ...] = ()


@dataclass(frozen=True, slots=True)
class FlowOnEnter:
    """Defines declarative behavior when entering a state."""

    instruction_template: str | None = None
    actions: tuple[str, ...] = ()
    on_fail: tuple[FlowFailure, ...] = ()


@dataclass(frozen=True, slots=True)
class PhoneSplitConfig:
    """Contains configuration reserved for a future phone split runtime."""

    segment_count: int
    max_full_resets: int
    silence_timeout_ms: int | None = None


@dataclass(frozen=True, slots=True)
class FlowState:
    """Defines dialog behavior configured for one booking state."""

    description: str | None
    on_enter: FlowOnEnter
    transitions: tuple[FlowTransition, ...]
    auto_transitions: tuple[FlowAutoTransition, ...] = ()
    phone_split_mode: PhoneSplitConfig | None = None
    terminal: bool = False


@dataclass(frozen=True, slots=True)
class FlowDefinition:
    """Contains a validated booking dialog flow definition."""

    version: str
    name: str
    description: str | None
    initial_state: BookingState
    states: dict[BookingState, FlowState]


@dataclass(frozen=True, slots=True)
class ChangeRule:
    """Defines one declarative in-progress booking change route."""

    reset_action: str
    next_state: BookingState
    applied_state: BookingState
    prompt_template: str


class InvalidFlowDefinitionError(ValueError):
    """Raised when a booking flow definition is invalid."""


class InvalidFlowConditionError(ValueError):
    """Raised when a flow condition has an invalid runtime configuration."""


class FlowLoader:
    """Loads and validates booking dialog flow definitions."""

    @staticmethod
    def load(path: Path) -> FlowDefinition:
        """Load a UTF-8 JSON flow definition from a filesystem path."""
        with path.open("r", encoding="utf-8") as flow_file:
            raw: object = json.load(flow_file)
        root = _object(raw, "Flow root must be a JSON object.")
        version = _required_string(root, "version", "Field 'version'")
        name = _required_string(root, "name", "Field 'name'")
        description = _optional_string(root.get("description"), "Field 'description'")
        initial_state = _state_value(root.get("initial_state"), "initial state")
        raw_states = _states_object(root.get("states"))
        declared = _declared_states(raw_states)
        if initial_state not in declared:
            raise InvalidFlowDefinitionError(
                f"Initial state '{initial_state.value}' is not declared in states."
            )
        states = {
            state: _parse_state(state.value, raw_definition, declared)
            for state, raw_definition in declared.items()
        }
        return FlowDefinition(version, name, description, initial_state, states)

    @staticmethod
    def load_change_handlers(path: Path) -> dict[str, ChangeRule]:
        """Load the compact target-to-change-rule mapping."""
        with path.open("r", encoding="utf-8") as handlers_file:
            raw: object = json.load(handlers_file)
        document = _object(raw, "Change handlers root must be a JSON object.")
        root = _object(
            document.get("change_handlers", document),
            "Change handlers must be a JSON object.",
        )
        allowed_targets = {
            "shop",
            "date",
            "people",
            "duration",
            "main_course",
            "time",
            "therapist",
            "phone",
        }
        if set(root) != allowed_targets:
            raise InvalidFlowDefinitionError(
                "Change handlers must define exactly the supported change targets."
            )
        return {
            target: _parse_change_rule(target, definition) for target, definition in root.items()
        }


def _parse_change_rule(target: str, raw: object) -> ChangeRule:
    value = _object(raw, f"Change handler '{target}' must be an object.")
    if set(value) != {
        "reset_action",
        "next_state",
        "applied_state",
        "prompt_template",
    }:
        raise InvalidFlowDefinitionError(f"Change handler '{target}' has an invalid schema.")
    reset_action = _required_string(
        value,
        "reset_action",
        f"Change handler '{target}' reset action",
    )
    prompt_template = _required_string(
        value,
        "prompt_template",
        f"Change handler '{target}' prompt template",
    )
    if not _ACTION_NAME_PATTERN.fullmatch(reset_action):
        raise InvalidFlowDefinitionError(
            f"Change handler '{target}' reset action must be snake_case."
        )
    if not _ACTION_NAME_PATTERN.fullmatch(prompt_template):
        raise InvalidFlowDefinitionError(
            f"Change handler '{target}' prompt template must be snake_case."
        )
    return ChangeRule(
        reset_action=reset_action,
        next_state=_state_value(
            value["next_state"],
            f"change handler '{target}' next state",
        ),
        applied_state=_state_value(
            value["applied_state"],
            f"change handler '{target}' applied state",
        ),
        prompt_template=prompt_template,
    )


def _object(raw: object, message: str) -> dict[str, object]:
    if not isinstance(raw, dict):
        raise InvalidFlowDefinitionError(message)
    return cast(dict[str, object], raw)


def _required_string(raw: dict[str, object], field: str, location: str) -> str:
    value = raw.get(field)
    if not isinstance(value, str) or value == "":
        raise InvalidFlowDefinitionError(f"{location} must be a non-empty string.")
    return value


def _optional_string(raw: object, location: str) -> str | None:
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise InvalidFlowDefinitionError(f"{location} must be a string or null.")
    return raw


def _state_value(raw: object, location: str) -> BookingState:
    if not isinstance(raw, str):
        raise InvalidFlowDefinitionError(f"Field '{location}' must be a string.")
    try:
        return BookingState(raw)
    except ValueError as exc:
        raise InvalidFlowDefinitionError(f"Unknown {location}: '{raw}'.") from exc


def _states_object(raw: object) -> dict[str, object]:
    states = _object(raw, "Field 'states' must be a JSON object.")
    if not states:
        raise InvalidFlowDefinitionError("Field 'states' must not be empty.")
    return states


def _declared_states(raw: dict[str, object]) -> dict[BookingState, object]:
    result: dict[BookingState, object] = {}
    for name, definition in raw.items():
        result[_state_value(name, "state")] = definition
    return result


def _parse_state(
    name: str,
    raw: object,
    declared: dict[BookingState, object],
) -> FlowState:
    definition = _object(raw, f"State '{name}' must be a JSON object.")
    description = _optional_string(
        definition.get("description"),
        f"State '{name}' field 'description'",
    )
    on_enter = _parse_on_enter(name, definition.get("on_enter"), declared)
    terminal = definition.get("terminal", False)
    if type(terminal) is not bool:
        raise InvalidFlowDefinitionError(f"State '{name}' field 'terminal' must be a boolean.")
    raw_transitions = definition.get("transitions")
    if not isinstance(raw_transitions, list):
        raise InvalidFlowDefinitionError(f"State '{name}' field 'transitions' must be a list.")
    if terminal and raw_transitions:
        raise InvalidFlowDefinitionError(f"Terminal state '{name}' must not define transitions.")
    transitions = tuple(
        _parse_transition(name, index, item, declared) for index, item in enumerate(raw_transitions)
    )
    auto_transitions = _parse_auto_transitions(name, definition, declared)
    if terminal and auto_transitions:
        raise InvalidFlowDefinitionError(
            f"Terminal state '{name}' must not define auto transitions."
        )
    if terminal and _FORBIDDEN_FAILURE_ACTIONS.intersection(on_enter.actions):
        raise InvalidFlowDefinitionError(
            f"Terminal state '{name}' must not execute booking side effects."
        )
    phone_split = _parse_phone_split(name, definition.get("phone_split_mode"))
    return FlowState(
        description=description,
        on_enter=on_enter,
        transitions=transitions,
        auto_transitions=auto_transitions,
        phone_split_mode=phone_split,
        terminal=cast(bool, terminal),
    )


def _parse_on_enter(
    state: str,
    raw: object,
    declared: dict[BookingState, object],
) -> FlowOnEnter:
    if raw is None:
        return FlowOnEnter()
    value = _object(raw, f"State '{state}' field 'on_enter' must be an object.")
    template = _optional_string(
        value.get("instruction_template"),
        f"State '{state}' on_enter instruction_template",
    )
    if template == "":
        raise InvalidFlowDefinitionError("Instruction template must not be empty.")
    actions = _actions(value.get("actions", []), f"state '{state}' on_enter")
    failures = _failures(value.get("on_fail"), state, declared)
    return FlowOnEnter(template, actions, failures)


def _parse_transition(
    state: str,
    index: int,
    raw: object,
    declared: dict[BookingState, object],
) -> FlowTransition:
    value = _object(raw, f"Transition {index} in state '{state}' must be an object.")
    intent = _required_string(value, "intent", f"Transition {index} intent")
    target = _target(value.get("target"), intent, state, declared)
    actions = _actions(value.get("actions", []), f"intent '{intent}' in state '{state}'")
    conditions = _conditions(value.get("conditions", []), f"intent '{intent}'")
    failures = _failures(value.get("on_fail"), state, declared)
    return FlowTransition(intent, target, actions, conditions, failures)


def _target(
    raw: object,
    label: str,
    state: str,
    declared: dict[BookingState, object],
) -> BookingState:
    target = _state_value(raw, "target state")
    if target not in declared:
        raise InvalidFlowDefinitionError(
            f"Unknown target state '{target.value}' for '{label}' in state '{state}'."
        )
    return target


def _actions(raw: object, location: str) -> tuple[str, ...]:
    if not isinstance(raw, list):
        raise InvalidFlowDefinitionError(f"Actions for {location} must be a list.")
    result: list[str] = []
    for action in raw:
        if not isinstance(action, str) or not _ACTION_NAME_PATTERN.fullmatch(action):
            raise InvalidFlowDefinitionError(
                f"Actions for {location} must contain snake_case identifiers."
            )
        if action in result:
            raise InvalidFlowDefinitionError(f"Duplicate action '{action}' for {location}.")
        result.append(action)
    return tuple(result)


def _conditions(raw: object, location: str) -> tuple[FlowCondition, ...]:
    if raw is None:
        return ()
    items = raw if isinstance(raw, list) else [raw]
    return tuple(_condition(item, location) for item in items)


def _condition(raw: object, location: str) -> FlowCondition:
    value = _object(raw, f"Condition for {location} must be an object.")
    op = _required_string(value, "op", f"Condition operator for {location}")
    if op not in SUPPORTED_OPERATORS:
        raise InvalidFlowDefinitionError(f"Unsupported condition operator '{op}'.")
    field = _optional_string(value.get("field"), f"Condition field for {location}")
    ref = _optional_string(value.get("ref"), f"Condition ref for {location}")
    nested_raw = value.get("conditions", [])
    if not isinstance(nested_raw, list):
        raise InvalidFlowDefinitionError("Nested conditions must be a list.")
    nested = tuple(_condition(item, location) for item in nested_raw)
    return FlowCondition(field, op, value.get("value"), ref, nested)


def _failures(
    raw: object,
    state: str,
    declared: dict[BookingState, object],
) -> tuple[FlowFailure, ...]:
    if raw is None:
        return ()
    items = raw if isinstance(raw, list) else [raw]
    result: list[FlowFailure] = []
    seen_conditions: set[str] = set()
    fallback_condition: str | None = None
    for item in items:
        value = _object(item, f"Failure in state '{state}' must be an object.")
        condition = _required_string(value, "condition", "Failure condition")
        if condition.strip() != condition:
            raise InvalidFlowDefinitionError(
                "Failure condition must not contain surrounding whitespace."
            )
        if condition in seen_conditions:
            raise InvalidFlowDefinitionError(
                f"Duplicate failure condition '{condition}' in state '{state}'."
            )
        if condition in {"*", "default"}:
            if fallback_condition is not None:
                raise InvalidFlowDefinitionError(
                    "Failure routes may define only one fallback condition."
                )
            fallback_condition = condition
        seen_conditions.add(condition)
        target = _target(value.get("target"), condition, state, declared)
        actions = _actions(value.get("actions", []), f"failure '{condition}'")
        if _FORBIDDEN_FAILURE_ACTIONS.intersection(actions):
            raise InvalidFlowDefinitionError("Failure actions must not create or retry a booking.")
        template = _optional_string(
            value.get("instruction_template"),
            f"Failure '{condition}' instruction_template",
        )
        if template == "":
            raise InvalidFlowDefinitionError(
                f"Failure '{condition}' instruction_template must not be empty."
            )
        result.append(FlowFailure(condition, target, actions, template))
    return tuple(result)


def _parse_auto_transitions(
    state: str,
    definition: dict[str, object],
    declared: dict[BookingState, object],
) -> tuple[FlowAutoTransition, ...]:
    items: list[object] = []
    if definition.get("auto_transition") is not None:
        items.append(definition["auto_transition"])
    raw_many = definition.get("auto_transitions", [])
    if not isinstance(raw_many, list):
        raise InvalidFlowDefinitionError(f"State '{state}' auto_transitions must be a list.")
    items.extend(raw_many)
    result: list[FlowAutoTransition] = []
    for item in items:
        value = _object(item, f"Auto transition in state '{state}' must be an object.")
        condition = _condition(value.get("condition"), f"auto transition in '{state}'")
        target = _target(value.get("target"), "auto transition", state, declared)
        actions = _actions(value.get("actions", []), f"auto transition in '{state}'")
        failures = _failures(value.get("on_fail"), state, declared)
        result.append(FlowAutoTransition(condition, target, actions, failures))
    return tuple(result)


def _parse_phone_split(state: str, raw: object) -> PhoneSplitConfig | None:
    if raw is None:
        return None
    value = _object(raw, f"State '{state}' phone_split_mode must be an object.")
    segment_count = value.get("segment_count")
    max_resets = value.get("max_full_resets")
    timeout = value.get("silence_timeout_ms")
    if type(segment_count) is not int or cast(int, segment_count) <= 0:
        raise InvalidFlowDefinitionError("Phone segment_count must be a positive integer.")
    if type(max_resets) is not int or cast(int, max_resets) < 0:
        raise InvalidFlowDefinitionError("Phone max_full_resets must be non-negative.")
    if timeout is not None and (type(timeout) is not int or cast(int, timeout) <= 0):
        raise InvalidFlowDefinitionError(
            "Phone silence_timeout_ms must be a positive integer or null."
        )
    return PhoneSplitConfig(
        cast(int, segment_count),
        cast(int, max_resets),
        cast(int | None, timeout),
    )
