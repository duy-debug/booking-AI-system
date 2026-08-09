"""Resolve conditional declarative booking conversation transitions."""

import logging
import operator
from enum import Enum
from typing import Any, Protocol, cast

from app.dialog.flow_loader import (
    SUPPORTED_OPERATORS,
    FlowAutoTransition,
    FlowCondition,
    FlowDefinition,
    FlowFailure,
    FlowState,
    FlowTransition,
    InvalidFlowConditionError,
    PhoneSplitConfig,
)
from app.domain.booking_context import BookingContext
from app.domain.booking_models import InvalidBookingStateError
from app.domain.booking_state import BookingState
from app.infrastructure.context_store import trace_log


class FailureSource(Protocol):
    """Exposes declarative failure routes to the resolver."""

    @property
    def on_fail(self) -> tuple[FlowFailure, ...]:
        """Return failure routes in declaration order."""
        ...


class StateMachine:
    """Evaluates conditions and resolves transitions without executing actions."""

    _COLLECTION_TYPES = (tuple, list, set, frozenset)

    # Giữ flow đã parse để mọi transition đều dựa trên cùng một định nghĩa khai báo.
    def __init__(self, flow: FlowDefinition) -> None:
        self._flow = flow

    # Đọc giá trị field trong BookingContext cho điều kiện declarative của flow.
    def _resolve_field(
        self,
        context: BookingContext,
        field_path: str,
    ) -> object | None:
        if field_path == "":
            raise InvalidFlowConditionError("Condition field path must not be empty.")

        current: object | None = context
        for segment in field_path.split("."):
            if segment == "":
                raise InvalidFlowConditionError(
                    "Condition field path must not contain empty segments."
                )
            if segment.startswith("_"):
                raise InvalidFlowConditionError(
                    "Condition field path must not access private attributes."
                )
            if current is None:
                return None
            current = getattr(current, segment, None)
            if callable(current):
                return None
        return current

    # Chuẩn hóa enum/collection trước khi so sánh điều kiện trong state machine.
    def _normalize_value(self, value: object) -> object:
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, tuple):
            return tuple(self._normalize_value(item) for item in value)
        if isinstance(value, list):
            return [self._normalize_value(item) for item in value]
        if isinstance(value, set):
            return {self._normalize_value(item) for item in value}
        if isinstance(value, frozenset):
            return frozenset(self._normalize_value(item) for item in value)
        return value

    # Đánh giá một điều kiện flow mà không làm thay đổi BookingContext.
    def _evaluate_condition(
        self,
        condition: FlowCondition,
        context: BookingContext,
    ) -> bool:
        op = condition.op
        if op not in SUPPORTED_OPERATORS:
            raise InvalidFlowConditionError(f"Unsupported condition operator '{op}'.")

        if op in {"and", "or"}:
            if condition.field is not None:
                raise InvalidFlowConditionError(f"Operator '{op}' must not define a field.")
            if not condition.conditions:
                raise InvalidFlowConditionError(
                    f"Operator '{op}' requires at least one child condition."
                )
            results = (self._evaluate_condition(child, context) for child in condition.conditions)
            return all(results) if op == "and" else any(results)

        if condition.field is None:
            raise InvalidFlowConditionError(f"Operator '{op}' requires a field.")

        actual = self._resolve_field(context, condition.field)
        if op == "in":
            has_value = condition.value is not None
            has_ref = condition.ref is not None
            if has_value == has_ref:
                raise InvalidFlowConditionError(
                    "Operator 'in' requires exactly one of value or ref."
                )
            collection = (
                condition.value if has_value else self._resolve_field(context, condition.ref or "")
            )
            if actual is None or not isinstance(
                collection,
                self._COLLECTION_TYPES,
            ):
                return False
            normalized_collection = tuple(self._normalize_value(item) for item in collection)
            try:
                return operator.contains(
                    normalized_collection,
                    self._normalize_value(actual),
                )
            except TypeError:
                return False

        if op == "null":
            return actual is None
        if op == "not_null":
            return actual is not None
        if actual is None:
            return False

        normalized_actual = self._normalize_value(actual)
        if op == "eq":
            return normalized_actual == self._normalize_value(condition.value)
        if op in {"gte", "lte"}:
            normalized_expected = self._normalize_value(condition.value)
            try:
                comparator = operator.ge if op == "gte" else operator.le
                return bool(
                    comparator(
                        cast(Any, normalized_actual),
                        cast(Any, normalized_expected),
                    )
                )
            except TypeError:
                return False
        raise InvalidFlowConditionError(f"Unsupported condition operator '{op}'.")

    # Kiểm tra toàn bộ điều kiện của một transition có khớp context hiện tại không.
    def _matches_conditions(
        self,
        conditions: tuple[FlowCondition, ...],
        context: BookingContext,
    ) -> bool:
        return all(self._evaluate_condition(condition, context) for condition in conditions)

    # Tìm transition phù hợp với state hiện tại và intent đã được NLU chọn.
    def resolve_transition(
        self,
        context: BookingContext,
        intent: str,
    ) -> FlowTransition:
        """Resolve the first matching exact candidate, then wildcard fallback."""
        state = self.get_state_definition(context.state)
        if state.terminal:
            raise InvalidBookingStateError(
                f"Cannot transition from terminal state '{context.state.value}'."
            )

        exact = tuple(item for item in state.transitions if item.intent == intent)
        resolved = self._resolve_candidates(exact, context)
        if resolved is not None:
            self._log_resolved(context, intent, resolved)
            return resolved

        wildcard = tuple(item for item in state.transitions if item.intent == "*")
        resolved = self._resolve_candidates(wildcard, context)
        if resolved is not None:
            self._log_resolved(context, intent, resolved)
            return resolved

        trace_log(
            logging.getLogger(__name__),
            logging.WARNING,
            "StateMachine",
            "transition_rejected",
            current_state=context.state.value,
            intent=intent,
            reason="intent_not_allowed",
        )
        raise InvalidBookingStateError(
            f"Cannot transition from '{context.state.value}' using intent '{intent}'."
        )

    # Chọn candidate đầu tiên khớp điều kiện, fallback sang transition không có điều kiện.
    def _resolve_candidates(
        self,
        candidates: tuple[FlowTransition, ...],
        context: BookingContext,
    ) -> FlowTransition | None:
        for transition in candidates:
            if transition.conditions and self._matches_conditions(
                transition.conditions,
                context,
            ):
                return transition
        return next(
            (transition for transition in candidates if not transition.conditions),
            None,
        )

    # Tìm auto transition sau khi business action cập nhật context, nhưng chưa commit state.
    def resolve_auto_transition(
        self,
        context: BookingContext,
    ) -> FlowAutoTransition | None:
        """Return the first matching auto transition without applying it."""
        state = self.get_state_definition(context.state)
        if state.terminal:
            return None
        return next(
            (
                transition
                for transition in state.auto_transitions
                if self._evaluate_condition(transition.condition, context)
            ),
            None,
        )

    # Áp dụng state mới sau khi handler/action đã hoàn tất thành công.
    def apply_transition(
        self,
        context: BookingContext,
        transition: FlowTransition | FlowAutoTransition,
    ) -> None:
        # State Machine là nguồn duy nhất commit state transition của booking flow.
        """Commit only the resolved target state."""
        previous_state = context.state
        context.state = transition.target
        trace_log(
            logging.getLogger(__name__),
            logging.DEBUG,
            "StateMachine",
            "state_transition_completed",
            previous_state=previous_state.value,
            next_state=transition.target.value,
        )

    @staticmethod
    # Ghi trace transition đã chọn để dễ theo dõi state đi qua flow nào.
    def _log_resolved(
        context: BookingContext,
        intent: str,
        transition: FlowTransition,
    ) -> None:
        trace_log(
            logging.getLogger(__name__),
            logging.DEBUG,
            "StateMachine",
            "transition_resolved",
            current_state=context.state.value,
            intent=intent,
            actions=list(transition.actions),
            success_target=transition.target.value,
        )

    # Tìm failure transition theo mã lỗi business, ưu tiên exact code rồi mới fallback.
    def resolve_failure(
        self,
        transition: FailureSource,
        failure_code: str,
    ) -> FlowFailure | None:
        """Resolve an exact failure code before canonical fallback routes."""
        exact = next(
            (failure for failure in transition.on_fail if failure.condition == failure_code),
            None,
        )
        if exact is not None:
            return exact
        wildcard = next(
            (failure for failure in transition.on_fail if failure.condition == "*"),
            None,
        )
        if wildcard is not None:
            return wildcard
        return next(
            (failure for failure in transition.on_fail if failure.condition == "default"),
            None,
        )

    # Áp dụng failure state mà không commit thêm dữ liệu business không hợp lệ.
    def apply_failure(
        self,
        context: BookingContext,
        failure: FlowFailure,
    ) -> None:
        """Commit only a resolved failure target."""
        context.state = failure.target

    # Giữ alias cũ cho caller/test nhưng vẫn không tự commit state.
    def transition(
        self,
        context: BookingContext,
        intent: str,
    ) -> FlowTransition:
        """Compatibility alias for resolve_transition; does not commit state."""
        return self.resolve_transition(context, intent)

    # Kiểm tra intent có route hợp lệ ở state hiện tại mà không làm đổi context.
    def can_transition(
        self,
        context: BookingContext,
        intent: str,
    ) -> bool:
        """Return whether a matching transition exists without mutating context."""
        try:
            self.resolve_transition(context, intent)
        except InvalidBookingStateError:
            return False
        return True

    # Liệt kê các intent được khai báo cho state để phục vụ policy/audit.
    def available_events(
        self,
        current_state: BookingState,
    ) -> tuple[str, ...]:
        """Return unique configured intents in first-seen insertion order."""
        return tuple(
            dict.fromkeys(
                transition.intent
                for transition in self.get_state_definition(current_state).transitions
            )
        )

    # Lấy định nghĩa state đã parse hoặc fail fast nếu flow thiếu state.
    def get_state_definition(self, state: BookingState) -> FlowState:
        """Return the flow definition for a booking state."""
        try:
            return self._flow.states[state]
        except KeyError as exc:
            raise InvalidBookingStateError(
                f"State '{state.value}' is not declared in the flow."
            ) from exc

    # Trả auto transition khai báo để caller quyết định thời điểm đánh giá.
    def get_auto_transitions(
        self,
        state: BookingState,
    ) -> tuple[FlowAutoTransition, ...]:
        """Return parsed auto transitions without evaluating them."""
        return self.get_state_definition(state).auto_transitions

    # Lấy cấu hình tách luồng phone/customer mà không tự chạy logic phone.
    def get_phone_split_config(
        self,
        state: BookingState,
    ) -> PhoneSplitConfig | None:
        """Return phone split configuration without executing phone logic."""
        return self.get_state_definition(state).phone_split_mode
