"""Tests for extended declarative flow loading."""

import json
from pathlib import Path
from typing import cast

import pytest

from app.dialog.flow_loader import FlowLoader, InvalidFlowDefinitionError
from app.domain.booking_state import BookingState


def _flow() -> dict[str, object]:
    return {
        "version": "2.0",
        "name": "extended-flow",
        "description": "Extended flow.",
        "initial_state": "idle",
        "states": {
            "idle": {
                "on_enter": {
                    "instruction_template": "greeting",
                    "actions": ["initialize"],
                },
                "transitions": [
                    {
                        "intent": "start_booking",
                        "target": "selecting_therapist",
                        "conditions": [
                            {"field": "num_customer", "op": "eq", "value": 1}
                        ],
                        "actions": ["start"],
                        "on_fail": {
                            "condition": "invalid",
                            "target": "idle",
                            "actions": ["clarify"],
                        },
                    }
                ],
                "auto_transition": {
                    "condition": {
                        "field": "num_customer",
                        "op": "gte",
                        "value": 2,
                    },
                    "target": "collecting_phone",
                    "actions": ["skip"],
                },
                "auto_transitions": [
                    {
                        "condition": {
                            "op": "and",
                            "conditions": [
                                {"field": "phone", "op": "not_null"},
                                {"field": "confirmed", "op": "eq", "value": True},
                            ],
                        },
                        "target": "completed",
                    }
                ],
                "rules": {"ignored": True},
            },
            "selecting_therapist": {
                "transitions": [
                    {
                        "intent": "select_therapist",
                        "target": "collecting_phone",
                        "on_fail": [
                            {
                                "condition": "not_found",
                                "target": "selecting_therapist",
                            },
                            {
                                "condition": "unavailable",
                                "target": "selecting_therapist",
                                "instruction_template": "therapist_unavailable",
                            },
                        ],
                    }
                ]
            },
            "collecting_phone": {
                "transitions": [
                    {"intent": "provide_phone", "target": "completed"}
                ],
                "phone_split_mode": {
                    "segment_count": 3,
                    "max_full_resets": 3,
                    "silence_timeout_ms": 5000,
                    "description": "ignored",
                },
            },
            "completed": {"transitions": [], "terminal": True},
        },
    }


def _write(tmp_path: Path, payload: object) -> Path:
    path = tmp_path / "flow.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _states(payload: dict[str, object]) -> dict[str, object]:
    return cast(dict[str, object], payload["states"])


def test_loads_conditions_failures_auto_transitions_and_on_enter(tmp_path: Path) -> None:
    flow = FlowLoader.load(_write(tmp_path, _flow()))
    idle = flow.states[BookingState.IDLE]
    transition = idle.transitions[0]

    assert idle.on_enter.instruction_template == "greeting"
    assert idle.on_enter.actions == ("initialize",)
    assert transition.conditions[0].field == "num_customer"
    assert transition.conditions[0].op == "eq"
    assert transition.on_fail[0].condition == "invalid"
    assert len(idle.auto_transitions) == 2
    assert idle.auto_transitions[0].condition.op == "gte"
    assert idle.auto_transitions[1].condition.op == "and"
    assert len(idle.auto_transitions[1].condition.conditions) == 2


def test_on_fail_object_and_list_are_normalized_to_tuples(tmp_path: Path) -> None:
    flow = FlowLoader.load(_write(tmp_path, _flow()))

    object_failure = flow.states[BookingState.IDLE].transitions[0].on_fail
    list_failures = flow.states[BookingState.SELECTING_THERAPIST].transitions[0].on_fail

    assert isinstance(object_failure, tuple)
    assert len(object_failure) == 1
    assert len(list_failures) == 2
    assert list_failures[1].instruction_template == "therapist_unavailable"


def test_phone_split_config_is_parsed_without_unsupported_fields(tmp_path: Path) -> None:
    flow = FlowLoader.load(_write(tmp_path, _flow()))
    config = flow.states[BookingState.COLLECTING_PHONE].phone_split_mode

    assert config is not None
    assert config.segment_count == 3
    assert config.max_full_resets == 3
    assert config.silence_timeout_ms == 5000


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("segment_count", 0),
        ("segment_count", True),
        ("max_full_resets", -1),
        ("silence_timeout_ms", 0),
        ("silence_timeout_ms", "5000"),
    ],
)
def test_invalid_phone_split_config_raises(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    payload = _flow()
    phone_state = cast(dict[str, object], _states(payload)["collecting_phone"])
    config = cast(dict[str, object], phone_state["phone_split_mode"])
    config[field] = value

    with pytest.raises(InvalidFlowDefinitionError):
        FlowLoader.load(_write(tmp_path, payload))


def test_invalid_condition_operator_raises(tmp_path: Path) -> None:
    payload = _flow()
    idle = cast(dict[str, object], _states(payload)["idle"])
    transitions = cast(list[dict[str, object]], idle["transitions"])
    conditions = cast(list[dict[str, object]], transitions[0]["conditions"])
    conditions[0]["op"] = "invalid"

    with pytest.raises(InvalidFlowDefinitionError, match="Unsupported condition"):
        FlowLoader.load(_write(tmp_path, payload))


def test_invalid_auto_transition_target_raises(tmp_path: Path) -> None:
    payload = _flow()
    idle = cast(dict[str, object], _states(payload)["idle"])
    auto = cast(dict[str, object], idle["auto_transition"])
    auto["target"] = "selecting_date"

    with pytest.raises(InvalidFlowDefinitionError, match="Unknown target state"):
        FlowLoader.load(_write(tmp_path, payload))


def test_terminal_state_rejects_auto_transitions(tmp_path: Path) -> None:
    payload = _flow()
    completed = cast(dict[str, object], _states(payload)["completed"])
    completed["auto_transition"] = {
        "condition": {"field": "booking", "op": "not_null"},
        "target": "completed",
    }

    with pytest.raises(
        InvalidFlowDefinitionError,
        match="must not define auto transitions",
    ):
        FlowLoader.load(_write(tmp_path, payload))


def test_duplicate_intents_are_preserved_for_future_condition_evaluation(
    tmp_path: Path,
) -> None:
    payload = _flow()
    idle = cast(dict[str, object], _states(payload)["idle"])
    transitions = cast(list[dict[str, object]], idle["transitions"])
    transitions.append(
        {
            "intent": "start_booking",
            "target": "collecting_phone",
            "conditions": [{"field": "num_customer", "op": "gte", "value": 2}],
        }
    )

    flow = FlowLoader.load(_write(tmp_path, payload))

    assert len(flow.states[BookingState.IDLE].transitions) == 2


def test_file_and_json_errors_are_propagated(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        FlowLoader.load(tmp_path / "missing.json")

    invalid = tmp_path / "invalid.json"
    invalid.write_text("{invalid", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        FlowLoader.load(invalid)
