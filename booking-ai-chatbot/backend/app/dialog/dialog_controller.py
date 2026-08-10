# Điều phối trọn một lượt hội thoại từ message đầu vào đến response cuối.

from __future__ import annotations

import logging
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from datetime import time as clock_time
from enum import StrEnum
from time import perf_counter
from types import MappingProxyType
from typing import TYPE_CHECKING, TypeVar, cast

from app.application.action_registry import (
    ActionExecutionContext,
    ActionExecutionError,
    ActionExecutionReport,
    ActionRegistry,
    ActionRegistryError,
)
from app.application.handlers.check_availability_handler import CheckAvailabilityHandler
from app.application.handlers.search_course_handler import SearchCourseHandler
from app.application.handlers.search_shop_handler import SearchShopHandler
from app.dialog.flow_loader import (
    ChangeRule,
    FlowAutoTransition,
    FlowDefinition,
    FlowFailure,
    FlowOnEnter,
    FlowTransition,
)
from app.dialog.nlu import (
    EntityResolutionResult,
    EntityResolutionStatus,
    NLUEntityKind,
    NLUResolutionStatus,
    NLUResult,
    NLUSource,
    entity_resolution_to_dialog_turn_input,
    to_dialog_turn_input,
)
from app.dialog.state_machine import StateMachine
from app.domain.booking_context import BookingContext, CourseSelectionMode
from app.domain.booking_models import (
    AvailableTherapistRequest,
    Course,
    CourseType,
    Shop,
    ShopSearchCriteria,
    TherapistAvailabilityGateway,
    TherapistPreference,
)
from app.domain.booking_state import BookingState
from app.domain.outcomes import HandlerOutcome, HandlerResult
from app.infrastructure.context_store import (
    begin_turn_metrics,
    bind_conversation,
    bind_correlation_id,
    bind_trace_context,
    bind_turn,
    elapsed_ms,
    record_turn_metrics,
    reset_conversation,
    reset_correlation_id,
    reset_trace_context,
    reset_turn,
    reset_turn_metrics,
    store_completed_turn_metrics,
    trace_log,
)

if TYPE_CHECKING:
    from app.dependencies import ApplicationContainer
    from app.dialog.instruction_builder import DialogResponse

logger = logging.getLogger(__name__)
T = TypeVar("T")

_UNRESOLVED_TEXT = {
    BookingState.IDLE: "Tôi chưa hiểu yêu cầu. Bạn có thể nói: Tôi muốn đặt lịch.",
    BookingState.SELECTING_SHOP: "Vui lòng cho biết cửa hàng hoặc khu vực bạn muốn đặt.",
    BookingState.SELECTING_DATE: "Vui lòng nhập ngày, ví dụ: ngày mai hoặc 15/08.",
    BookingState.SELECTING_PEOPLE: "Vui lòng cho biết số người từ 1 đến 3.",
    BookingState.SELECTING_DURATION: "Vui lòng nhập thời lượng, ví dụ: 60 phút.",
    BookingState.SELECTING_SERVICE: "Vui lòng nhập tên liệu trình bạn muốn chọn.",
    BookingState.SELECTING_TIME: "Vui lòng nhập giờ rõ ràng, ví dụ: 19:00 hoặc 7 giờ tối.",
    BookingState.SELECTING_THERAPIST: "Bạn có thể chọn Nam, Nữ hoặc Không yêu cầu.",
    BookingState.COLLECTING_PHONE: "Vui lòng nhập số điện thoại hợp lệ.",
    BookingState.COLLECTING_NAME: "Vui lòng nhập tên khách hàng.",
}
_AMBIGUOUS_TEXT = {
    NLUEntityKind.SHOP: "Đã tìm thấy nhiều cửa hàng phù hợp. Vui lòng chọn một cửa hàng.",
    NLUEntityKind.COURSE: "Đã tìm thấy nhiều liệu trình phù hợp. Vui lòng chọn một liệu trình.",
    NLUEntityKind.THERAPIST: (
        "Đã tìm thấy nhiều kỹ thuật viên phù hợp. Vui lòng chọn một kỹ thuật viên."
    ),
}
_NOT_FOUND_TEXT = {
    NLUEntityKind.SHOP: "Không tìm thấy cửa hàng phù hợp. Vui lòng nhập lại tên hoặc khu vực.",
    NLUEntityKind.COURSE: "Không tìm thấy liệu trình phù hợp. Vui lòng nhập lại tên liệu trình.",
    NLUEntityKind.THERAPIST: "Không tìm thấy kỹ thuật viên phù hợp.",
}
_UNSUPPORTED_TEXT = {
    NLUEntityKind.SHOP: "Hiện tại hệ thống chưa hỗ trợ tra cứu cửa hàng này.",
    NLUEntityKind.COURSE: "Hiện tại hệ thống chưa hỗ trợ tra cứu liệu trình này.",
    NLUEntityKind.THERAPIST: (
        "Hiện tại hệ thống chưa hỗ trợ tìm kỹ thuật viên theo tên. "
        "Bạn có thể chọn Nam, Nữ hoặc Không yêu cầu."
    ),
}
_ENTITY_FAILURE_TEXT = "Hệ thống chưa thể tra cứu thông tin lúc này. Vui lòng thử lại."
_DEFAULT_UNRESOLVED_TEXT = "Tôi chưa hiểu yêu cầu. Vui lòng nhập lại rõ hơn."
_RECOVERY_QUICK_REPLIES = {
    BookingState.IDLE: ("Tôi muốn đặt lịch", "Xem danh sách cửa hàng"),
    BookingState.SELECTING_DATE: ("Hôm nay", "Ngày mai"),
    BookingState.SELECTING_PEOPLE: ("1 người", "2 người", "3 người"),
    BookingState.SELECTING_DURATION: ("45 phút", "60 phút", "90 phút"),
    BookingState.SELECTING_THERAPIST: ("Không yêu cầu", "Nam", "Nữ"),
    BookingState.VERIFYING_PHONE: ("Xác nhận", "Nhập lại"),
    BookingState.AWAITING_CONFIRMATION: ("Xác nhận", "Chỉnh sửa", "Hủy"),
    BookingState.BOOKING_FAILED: ("Thử lại", "Chọn giờ khác", "Hủy"),
}
_TERMINAL_CHANGE_TEXT = (
    "Đặt lịch này đã hoàn tất. Vui lòng tạo yêu cầu mới để thay đổi hoặc hủy lịch."
)


class DialogControllerError(Exception):
    # Lỗi gốc của tầng điều phối dialog.
    pass


class InvalidDialogTurnError(DialogControllerError):
    # Phát sinh khi một turn đã parse sẵn không đúng contract đầu vào.
    pass


class AutoTransitionLimitError(DialogControllerError):
    # Phát sinh khi một turn chạy quá số auto transition cho phép.
    pass


class AutoTransitionCycleError(DialogControllerError):
    # Phát sinh khi auto transition bị lặp vòng trong cùng một turn.
    pass


@dataclass(frozen=True, slots=True)
class DialogTurnInput:
    # Biểu diễn intent/payload đã được chuẩn hóa và sẵn sàng cho dialog flow.

    intent: str
    payload: Mapping[str, object]
    idempotency_key: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.intent, str) or not self.intent.strip():
            raise InvalidDialogTurnError("Dialog intent must be a non-empty string.")
        if not isinstance(self.payload, Mapping):
            raise InvalidDialogTurnError("Dialog payload must be a mapping.")
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))


class DialogTurnStatus(StrEnum):
    # Mô tả turn đã thành công, recovery được hay thất bại chưa xử lý.

    SUCCESS = "success"
    FAILURE_HANDLED = "failure_handled"
    FAILURE_UNHANDLED = "failure_unhandled"


@dataclass(frozen=True, slots=True)
class DialogTurnResult:
    # Kết quả điều phối turn trước khi dựng câu trả lời cuối cùng.

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
    # Điều phối một lượt hội thoại hoàn chỉnh của chatbot.
    # Controller này nhận message từ transport, tải `BookingContext`, gọi NLU,
    # route sang nhánh entity resolution / FAQ / dialog flow, chạy state + action,
    # dựng response và lưu lại context nếu turn xử lý thành công.

    # Nhận StateMachine, ActionRegistry và change rules để điều phối một dialog turn.
    def __init__(
        self,
        *,
        flow: FlowDefinition,
        state_machine: StateMachine,
        action_registry: ActionRegistry,
        change_rules: Mapping[str, ChangeRule] | None = None,
        max_auto_transitions: int = 8,
    ) -> None:
        if type(max_auto_transitions) is not int or max_auto_transitions < 1:
            raise ValueError("max_auto_transitions must be at least one.")
        self._flow = flow
        self._state_machine = state_machine
        self._action_registry = action_registry
        self._change_rules = dict(change_rules or {})
        self._max_auto_transitions = max_auto_transitions
        self._runtime: ApplicationContainer | None = None

    # Bind composition graph sau khi toàn bộ dependency đã được tạo ở application container.
    def bind_runtime(self, runtime: "ApplicationContainer") -> None:
        # Bind toàn bộ dependency runtime sau khi composition root đã hoàn tất.
        if self._runtime is not None and self._runtime is not runtime:
            raise RuntimeError("DialogController runtime is already bound.")
        self._runtime = runtime

    # Nhận message từ API, khóa conversation và chạy trọn một lượt xử lý hội thoại.
    async def handle_message(
        self,
        *,
        conversation_id: str,
        message: str,
        idempotency_key: str | None = None,
        correlation_id: str | None = None,
        entrypoint: str | None = None,
    ) -> "DialogResponse":
        # Chạy trọn một turn từ load context đến response generation và save context.
        if self._runtime is None:
            raise RuntimeError("DialogController runtime is not bound.")
        runtime = self._runtime
        async with runtime.conversation_context_store.conversation_lock(conversation_id):
            return await _process_serialized_chat_message(
                conversation_id=conversation_id,
                message=message,
                idempotency_key=idempotency_key,
                container=runtime,
                correlation_id=correlation_id,
                entrypoint=entrypoint,
            )

    # Chạy một turn đã parse sẵn qua StateMachine và ActionRegistry, chưa render response cuối.
    async def handle_turn(
        self,
        booking_context: BookingContext,
        turn: DialogTurnInput,
    ) -> DialogTurnResult:
        # Chạy một turn đã parse sẵn qua state machine và action registry.
        initial_state = booking_context.state
        if initial_state is BookingState.COMPLETED and turn.intent == "confirm":
            return self._success_result(
                booking_context=booking_context,
                initial_state=initial_state,
                intent=turn.intent,
                instruction_template="booking_complete",
                committed_actions=(),
                auto_transition_count=0,
            )
        # Final confirm cần idempotency key trước khi state BOOKING_EXECUTING gọi POS create.
        if turn.intent == "confirm" and initial_state in {
            BookingState.AWAITING_CONFIRMATION,
            BookingState.BOOKING_FAILED,
        }:
            booking_context.ensure_booking_attempt_id()
        action_context = ActionExecutionContext(
            booking_context=booking_context,
            intent=turn.intent,
            payload=turn.payload,
            idempotency_key=booking_context.booking_attempt_id,
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

        # Chạy action của transition trên working context để rollback nếu action fail.
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
        # Chỉ commit state sau khi action chính đã thành công.
        self._state_machine.apply_transition(booking_context, transition)
        if booking_context.state is BookingState.CANCELLED:
            booking_context.clear_booking_attempt()
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

    # Tạo transition tạm cho change_info dựa trên field cần sửa và có value hay chưa.
    def _change_transition(
        self,
        booking_context: BookingContext,
        turn: DialogTurnInput,
    ) -> tuple[ChangeRule, FlowTransition, bool]:
        target = turn.payload.get("change_target")
        if not isinstance(target, str):
            raise InvalidDialogTurnError("A booking change requires a supported change target.")
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

    # Chạy auto transition sau khi context đủ điều kiện, ví dụ booking success sang completed.
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
            auto_transition = self._state_machine.resolve_auto_transition(booking_context)
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
        failure_code = self._action_registry.get_failure_code(error)
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
        if failure_code in {"no_slots_available", "no_working_shift"}:
            booking_context.last_unavailable_date = booking_context.booking_date
        return DialogTurnResult(
            status=DialogTurnStatus.FAILURE_HANDLED,
            initial_state=initial_state,
            final_state=booking_context.state,
            intent=intent,
            instruction_template=failure.instruction_template,
            executed_actions=(committed_actions + failure_report.executed_action_names),
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
            return await self._action_registry.execute_actions(
                action_names,
                action_context,
            )
        except ActionExecutionError:
            raise
        except ActionRegistryError as error:
            action_name = self._error_action_name(action_names)
            raise ActionExecutionError(action_name, (), error) from error

    async def _execute_failure_actions(
        self,
        failure: FlowFailure,
        action_context: ActionExecutionContext,
    ) -> ActionExecutionReport:
        try:
            return await self._action_registry.execute_failure_actions(
                failure,
                action_context,
            )
        except ActionExecutionError:
            raise
        except ActionRegistryError as error:
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
            raise AutoTransitionLimitError("Maximum auto transitions exceeded for one turn.")
        signature = (source_state, transition.target, transition.actions)
        if signature in seen:
            raise AutoTransitionCycleError("An auto-transition signature repeated in one turn.")
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


async def _process_serialized_chat_message(
    *,
    conversation_id: str,
    message: str,
    idempotency_key: str | None,
    container: ApplicationContainer,
    correlation_id: str | None = None,
    entrypoint: str | None = None,
) -> DialogResponse:
    # Gắn trace/conversation context rồi chạy pipeline message theo thứ tự an toàn.
    # Chạy pipeline xử lý message theo thứ tự an toàn mà không đổi business rules.
    token = bind_conversation(conversation_id)
    correlation_token = bind_correlation_id(correlation_id)
    started_at = perf_counter()
    context = await container.conversation_context_store.get_copy(conversation_id)
    turn_token = bind_turn(context.begin_turn())
    distributed_trace_token = bind_trace_context(
        trace_id=correlation_id,
        session_id=conversation_id,
        turn_id=context.turn_sequence,
    )
    metrics_token = begin_turn_metrics()
    initial_state = context.state
    trace_log(
        logger,
        logging.INFO,
        "[1] REQUEST",
        "request_started",
        method="POST",
        path=entrypoint or "unknown",
        message_length=len(message),
        state=initial_state.value,
    )
    _trace_context_loaded(context)
    trace_log(logger, logging.DEBUG, "DialogController", "turn_started", state=initial_state.value)
    if _local_debug_enabled("LOG_USER_MESSAGES"):
        trace_log(
            logger,
            logging.DEBUG,
            "Turn",
            "user_message",
            function="handle_message",
            user_message=message[:500],
        )
    try:
        # Phân tích NLU, route, chạy handler và dựng DialogResponse trên working context.
        response = await _process_bound_chat_message(
            conversation_id=conversation_id,
            message=message,
            idempotency_key=idempotency_key,
            container=container,
            context=context,
        )
        # LLM NLG chỉ diễn đạt response, không quyết định business outcome.
        if getattr(container, "llm_nlg_required", False):
            response = await container.response_generator.generate(
                response=response,
                context=context,
            )
        if response.status is not DialogTurnStatus.FAILURE_UNHANDLED:
            # Chỉ commit context sau khi toàn bộ handler/state pipeline đã thành công.
            await container.conversation_context_store.save(
                conversation_id,
                context,
            )
            _trace_context_saved(context)
        _log_instruction(response)
        trace_log(
            logger,
            logging.INFO,
            "[7] RESPONSE",
            "response_ready",
            state=response.state.value,
            status=response.status.value,
            text=response.text,
            quick_replies=list(response.quick_replies),
            instruction_template=response.instruction_template or "none",
        )
        if _local_debug_enabled("LOG_AI_MESSAGES"):
            trace_log(
                logger,
                logging.DEBUG,
                "ResponseGenerator",
                "ai_response_created",
                function="handle_message",
                assistant_message=response.text[:1000],
            )
        store_completed_turn_metrics()
        return response
    except Exception as error:
        trace_log(
            logger,
            logging.ERROR,
            "DialogController",
            "turn_failed",
            state=context.state.value,
            exception_type=type(error).__name__,
            duration_ms=elapsed_ms(started_at),
            _exc_info=True,
        )
        raise
    finally:
        reset_turn_metrics(metrics_token)
        reset_trace_context(distributed_trace_token)
        reset_turn(turn_token)
        reset_correlation_id(correlation_token)
        reset_conversation(token)


async def _process_bound_chat_message(
    *,
    conversation_id: str,
    message: str,
    idempotency_key: str | None,
    container: ApplicationContainer,
    context: BookingContext,
) -> DialogResponse:
    # Xử lý turn khi trace context đã bind: NLU -> route -> entity/action -> response.
    # Xử lý turn sau khi safe logging context đã được bind.
    # Phân tích câu người dùng bằng LLM NLU thành NLUResult canonical.
    nlu_result = await container.llm_nlu.parse(
        text=message,
        state=context.state,
        context=context,
    )
    # Stage entity đã nói sớm vào context để chỉ hỏi field còn thiếu.
    _stage_requested_entities(nlu_result, context)

    if context.state in {
        BookingState.COMPLETED,
        BookingState.CANCELLED,
    } and nlu_result.matched_rule in {
        "change_booking_field",
        "change_entity_query",
        "state_incompatible_change_info",
    }:
        return _handled_response(context, _TERMINAL_CHANGE_TEXT)

    record_turn_metrics(intent=nlu_result.intent or "unresolved")

    if nlu_result.intent in {"greeting", "thanks", "ask_why", "repeat_last_question"}:
        _trace_route("global_intent", "global_intent", nlu_result, context)
        if nlu_result.intent == "repeat_last_question" and context.last_failure_code in {
            "slot_api_error",
            "no_slots_available",
            "no_working_shift",
        }:
            return await _retry_availability(container=container, context=context)
        return _global_intent_response(nlu_result.intent, context)

    if nlu_result.intent == "restart_booking":
        _trace_route("restart", "llm", nlu_result, context)
        context.restart_booking()
        response = _global_intent_response("restart_booking", context)
        response = await _with_proactive_suggestions(
            response=response,
            container=container,
            context=context,
        )
        return response

    if nlu_result.intent in _DISCOVERY_INTENTS:
        _trace_route("discovery", "llm", nlu_result, context)
        response = await _handle_discovery(
            nlu_result=nlu_result,
            container=container,
            context=context,
        )
        return response

    if nlu_result.intent == "ask_question":
        _trace_route(
            "faq",
            "llm",
            nlu_result,
            context,
        )
        faq_turn = to_dialog_turn_input(
            nlu_result,
            state=context.state,
            intent_policy=container.state_intent_policy,
        )
        query = faq_turn.payload["query"]
        assert isinstance(query, str)
        response = await container.faq_manager.answer(
            query=query,
            context=context,
        )
        return response

    if nlu_result.intent == "change_info" and not nlu_result.payload:
        _trace_route("change_info_menu", "llm_generic_change", nlu_result, context)
        return _change_menu_response(context)

    if nlu_result.resolution_status is NLUResolutionStatus.UNRESOLVED:
        _trace_route("unresolved_recovery", "unresolved_recovery", nlu_result, context)
        return _handled_response(
            context,
            _UNRESOLVED_TEXT.get(context.state, _DEFAULT_UNRESOLVED_TEXT),
            _state_recovery_quick_replies(context),
        )

    if nlu_result.resolution_status is NLUResolutionStatus.ENTITY_RESOLUTION_REQUIRED:
        _trace_route("entity_resolution", "state_expected_entity", nlu_result, context)
        entity_kind = nlu_result.entity_kind
        assert entity_kind is not None
        resolution_started = perf_counter()
        resolution = await container.entity_resolution_coordinator.resolve(
            nlu_result=nlu_result,
            state=context.state,
            context=context,
        )
        resolution_duration_ms = elapsed_ms(resolution_started)
        trace_log(
            logger,
            logging.INFO,
            "[4] ENTITY RESOLUTION",
            "completed",
            entity=resolution.entity_kind.value,
            resolution_status=resolution.status.value,
            candidate_count=len(resolution.candidates),
            function="resolve",
            input_summary=f"state={context.state.value}, entity={entity_kind.value}",
            output_summary=f"matched={_matched_display_name(resolution)}",
            search_scope=context.state.value,
            error_code=resolution.failure_code or "none",
            duration_ms=resolution_duration_ms,
        )
        record_turn_metrics(entity_resolution_ms=resolution_duration_ms)
        if _local_debug_enabled("LOG_USER_MESSAGES"):
            trace_log(
                logger,
                logging.DEBUG,
                "EntityResolver",
                "query",
                function="resolve",
                query=message[:500],
                entity_type=entity_kind.value,
                search_scope=context.state.value,
            )
        if resolution.status is not EntityResolutionStatus.RESOLVED:
            return await _entity_response(context, resolution, container)
        turn = entity_resolution_to_dialog_turn_input(
            resolution,
            state=context.state,
            intent_policy=container.state_intent_policy,
            idempotency_key=idempotency_key,
        )
    else:
        _trace_route(
            "dialog",
            "llm",
            nlu_result,
            context,
        )
        turn = to_dialog_turn_input(
            nlu_result,
            state=context.state,
            intent_policy=container.state_intent_policy,
            idempotency_key=idempotency_key,
        )

    controller_started = perf_counter()
    result = await container.dialog_controller.handle_turn(context, turn)
    result = await _consume_requested_entities(
        container=container,
        context=context,
        result=result,
        idempotency_key=idempotency_key,
    )
    record_turn_metrics(
        intent=result.intent,
        handler=",".join(result.executed_actions) or "none",
        outcome=result.status.value,
        handler_duration_ms=elapsed_ms(controller_started),
    )
    trace_log(
        logger,
        logging.INFO,
        "[5] ROUTING",
        "state_actions_completed",
        from_state=result.initial_state.value,
        to_state=result.final_state.value,
        intent=result.intent,
        status=result.status.value,
        route="dialog",
        actions=list(result.executed_actions),
        error_code=result.failure_code or "none",
        duration_ms=elapsed_ms(controller_started),
    )
    if result.failure_code is not None:
        trace_log(
            logger,
            logging.WARNING,
            "DialogCtrl",
            "business_failure",
            error_code=result.failure_code,
            failed_action=result.failed_action or "none",
        )
    response = container.instruction_builder.build_response(
        result=result,
        context=context,
    )
    if result.status is DialogTurnStatus.SUCCESS:
        response = await _with_proactive_suggestions(
            response=response,
            container=container,
            context=context,
        )
    elif not response.quick_replies:
        response = _with_state_recovery_suggestions(response, context)
    return response


async def _consume_requested_entities(
    *,
    container: ApplicationContainer,
    context: BookingContext,
    result: DialogTurnResult,
    idempotency_key: str | None,
) -> DialogTurnResult:
    # Tiêu thụ các slot chờ đã validate theo đúng thứ tự workflow production.
    consumed = result
    for _ in range(12):
        if consumed.status is not DialogTurnStatus.SUCCESS:
            break
        follow_up = await _next_requested_turn(
            container=container,
            context=context,
            idempotency_key=idempotency_key,
        )
        if follow_up is None:
            break
        consumed = await container.dialog_controller.handle_turn(context, follow_up)
        trace_log(
            logger,
            logging.DEBUG,
            "DialogCtrl",
            "prefilled_entity_consumed",
            intent=follow_up.intent,
            from_state=consumed.initial_state.value,
            to_state=consumed.final_state.value,
            status=consumed.status.value,
        )
    return consumed


def _stage_requested_entities(result: NLUResult, context: BookingContext) -> None:
    # Lưu các entity phụ do LLM trích xuất cho tới khi workflow đi tới đúng state.
    if result.intent not in {
        "start_booking",
        "select_store",
        "select_date",
        "select_people",
        "select_duration",
        "select_course",
        "select_time",
        "select_therapist",
        "provide_phone",
        "provide_name",
        "change_info",
    } and result.resolution_status is not NLUResolutionStatus.ENTITY_RESOLUTION_REQUIRED:
        return

    entities = result.merged_entities
    primary = _primary_entity_keys(result, context)

    def requested_text(key: str) -> str | None:
        value = entities.get(key)
        if (
            key in primary
            or not _can_stage_requested_slot(key, context.state)
            or not isinstance(value, str)
        ):
            return None
        normalized = value.strip()
        return normalized or None

    shop_name = requested_text("shop_name")
    if shop_name is not None:
        context.requested_shop_name = shop_name
    booking_date = entities.get("booking_date")
    if (
        "booking_date" not in primary
        and _can_stage_requested_slot("booking_date", context.state)
        and type(booking_date) is date
    ):
        context.requested_booking_date = booking_date
    people = entities.get("number_of_people")
    if (
        "number_of_people" not in primary
        and _can_stage_requested_slot("number_of_people", context.state)
        and type(people) is int
    ):
        context.requested_num_customer = people
    duration = entities.get("duration_minutes")
    if (
        "duration_minutes" not in primary
        and _can_stage_requested_slot("duration_minutes", context.state)
        and type(duration) is int
    ):
        context.requested_duration_minutes = duration
    start_time = entities.get("start_time")
    if (
        "start_time" not in primary
        and _can_stage_requested_slot("start_time", context.state)
        and type(start_time) is time
    ):
        context.requested_start_time = start_time

    main_course = requested_text("main_course_name")
    generic_course = requested_text("service_name")
    addon = requested_text("addon_name")
    if main_course is not None:
        context.requested_main_course_name = main_course
    elif generic_course is not None:
        if context.course_selection_mode is CourseSelectionMode.ADDON:
            context.requested_addon_name = generic_course
        else:
            context.requested_main_course_name = generic_course
    if addon is not None:
        context.requested_addon_name = addon
        context.requested_skip_addon = False
    skip_addon = entities.get("skip_addon")
    if (
        addon is None
        and "skip_addon" not in primary
        and _can_stage_requested_slot("skip_addon", context.state)
        and type(skip_addon) is bool
    ):
        context.requested_skip_addon = skip_addon

    therapist_name = requested_text("therapist_name")
    if therapist_name is not None:
        context.requested_therapist_name = therapist_name
    therapist_gender = requested_text("therapist_gender")
    if therapist_gender is not None:
        context.requested_therapist_gender = therapist_gender
    phone = requested_text("phone")
    if phone is not None:
        context.requested_phone = phone
    customer_name = requested_text("customer_name")
    if customer_name is not None:
        context.requested_customer_name = customer_name


def _can_stage_requested_slot(key: str, state: BookingState) -> bool:
    state_order = {
        BookingState.IDLE: 0,
        BookingState.SELECTING_SHOP: 1,
        BookingState.SELECTING_DATE: 2,
        BookingState.SELECTING_PEOPLE: 3,
        BookingState.SELECTING_DURATION: 4,
        BookingState.SELECTING_SERVICE: 5,
        BookingState.SELECTING_TIME: 6,
        BookingState.SELECTING_THERAPIST: 7,
        BookingState.COLLECTING_PHONE: 8,
        BookingState.VERIFYING_PHONE: 9,
        BookingState.COLLECTING_NAME: 10,
        BookingState.AWAITING_CONFIRMATION: 11,
        BookingState.BOOKING_EXECUTING: 12,
        BookingState.COMPLETED: 13,
        BookingState.BOOKING_FAILED: 13,
        BookingState.CANCELLED: 13,
    }
    slot_order = {
        "shop_name": 1,
        "booking_date": 2,
        "number_of_people": 3,
        "duration_minutes": 4,
        "service_name": 5,
        "main_course_name": 5,
        "addon_name": 5,
        "skip_addon": 5,
        "start_time": 6,
        "therapist_name": 7,
        "therapist_gender": 7,
        "phone": 8,
        "customer_name": 10,
    }
    return slot_order.get(key, 99) >= state_order[state]


def _primary_entity_keys(result: NLUResult, context: BookingContext) -> frozenset[str]:
    if result.intent == "start_booking":
        return frozenset()
    keys = {
        "select_store": {"shop_name"},
        "select_date": {"booking_date"},
        "select_people": {"number_of_people"},
        "select_duration": {"duration_minutes"},
        "select_time": {"start_time"},
        "select_therapist": {"therapist_name", "therapist_gender"},
        "provide_phone": {"phone"},
        "provide_name": {"customer_name"},
    }.get(result.intent or "", set())
    if result.entity_kind is NLUEntityKind.SHOP:
        keys.add("shop_name")
    elif result.entity_kind is NLUEntityKind.COURSE:
        keys.update(
            {"addon_name", "service_name"}
            if context.course_selection_mode is CourseSelectionMode.ADDON
            else {"main_course_name", "service_name"}
        )
    elif result.entity_kind is NLUEntityKind.THERAPIST:
        keys.update({"therapist_name", "therapist_gender"})
    return frozenset(keys)


async def _next_requested_turn(
    *,
    container: ApplicationContainer,
    context: BookingContext,
    idempotency_key: str | None,
) -> DialogTurnInput | None:
    direct: tuple[str, str, Mapping[str, object]] | None = None
    entity: tuple[str, NLUEntityKind] | None = None
    if context.state is BookingState.SELECTING_SHOP and context.requested_shop_name:
        shop_query, context.requested_shop_name = context.requested_shop_name, None
        entity = (shop_query, NLUEntityKind.SHOP)
    elif context.state is BookingState.SELECTING_DATE and context.requested_booking_date:
        requested_date, context.requested_booking_date = context.requested_booking_date, None
        direct = ("select_date", "booking_date", {"booking_date": requested_date})
    elif context.state is BookingState.SELECTING_PEOPLE and context.requested_num_customer:
        requested_people, context.requested_num_customer = context.requested_num_customer, None
        direct = ("select_people", "num_customer", {"num_customer": requested_people})
    elif (
        context.state is BookingState.SELECTING_PEOPLE
        and _should_resume_recovery(context)
        and context.num_customer is not None
    ):
        direct = ("select_people", "num_customer", {"num_customer": context.num_customer})
    elif context.state is BookingState.SELECTING_DURATION:
        if context.requested_duration_minutes is not None:
            requested_duration, context.requested_duration_minutes = (
                context.requested_duration_minutes,
                None,
            )
            direct = (
                "select_duration",
                "duration_minutes",
                {"duration_minutes": requested_duration},
            )
        elif _should_resume_recovery(context) and context.duration_minutes is not None:
            direct = (
                "select_duration",
                "duration_minutes",
                {"duration_minutes": context.duration_minutes},
            )
        elif context.requested_main_course_name:
            course_query, context.requested_main_course_name = (
                context.requested_main_course_name,
                None,
            )
            entity = (course_query, NLUEntityKind.COURSE)
    elif context.state is BookingState.SELECTING_SERVICE:
        if context.main_course is None and context.requested_main_course_name:
            main_query, context.requested_main_course_name = (
                context.requested_main_course_name,
                None,
            )
            entity = (main_query, NLUEntityKind.COURSE)
        elif context.main_course is not None and context.requested_addon_name:
            addon_query, context.requested_addon_name = context.requested_addon_name, None
            entity = (addon_query, NLUEntityKind.COURSE)
        elif context.main_course is not None and context.requested_skip_addon:
            context.requested_skip_addon = False
            direct = ("deny", "skip_addon", {})
        elif (
            _should_resume_recovery(context)
            and context.main_course is not None
            and context.course_selection_mode is CourseSelectionMode.NONE
        ):
            direct = ("deny", "skip_addon", {})
    elif context.state is BookingState.SELECTING_TIME and context.requested_start_time:
        requested_time, context.requested_start_time = context.requested_start_time, None
        direct = ("select_time", "start_time", {"start_time": requested_time})
    elif context.state is BookingState.SELECTING_THERAPIST:
        therapist_query = context.requested_therapist_name or context.requested_therapist_gender
        context.requested_therapist_name = None
        context.requested_therapist_gender = None
        if therapist_query:
            entity = (therapist_query, NLUEntityKind.THERAPIST)
    elif context.state is BookingState.COLLECTING_PHONE and context.requested_phone:
        requested_phone, context.requested_phone = context.requested_phone, None
        direct = ("provide_phone", "phone", {"phone": requested_phone})
    elif context.state is BookingState.COLLECTING_NAME and context.requested_customer_name:
        requested_name, context.requested_customer_name = context.requested_customer_name, None
        direct = ("provide_name", "name", {"name": requested_name})

    if direct is not None:
        intent, _field, payload = direct
        return DialogTurnInput(intent, payload, idempotency_key=idempotency_key)
    if entity is None:
        return None
    query, kind = entity
    request = NLUResult(
        intent=None,
        payload={},
        confidence=1.0,
        source=NLUSource.CONTEXT,
        resolution_status=NLUResolutionStatus.ENTITY_RESOLUTION_REQUIRED,
        matched_rule="prefilled_entity",
        entity_query=query,
        entity_kind=kind,
    )
    resolution = await container.entity_resolution_coordinator.resolve(
        nlu_result=request,
        state=context.state,
        context=context,
    )
    if resolution.status is not EntityResolutionStatus.RESOLVED:
        trace_log(
            logger,
            logging.DEBUG,
            "EntityResolver",
            "prefilled_entity_not_consumed",
            entity=kind.value,
            resolution_status=resolution.status.value,
            candidate_count=len(resolution.candidates),
            error_code=resolution.failure_code or "none",
        )
        return None
    return entity_resolution_to_dialog_turn_input(
        resolution,
        state=context.state,
        intent_policy=container.state_intent_policy,
        idempotency_key=idempotency_key,
    )


# Ghi lý do router chọn nhánh xử lý để trace một chat turn trong terminal.
def _trace_route(
    route: str,
    reason: str,
    result: NLUResult,
    context: BookingContext,
) -> None:
    trace_log(
        logger,
        logging.INFO,
        "[5] ROUTING",
        "dispatch",
        caller="_process_bound_chat_message()",
        route=route,
        reason=reason,
        intent=result.intent or "unresolved",
        state=context.state.value,
    )


# Chụp snapshot context trước xử lý để so sánh diff sau turn.
# Lấy tên hiển thị của entity đã resolve để trace mà không lộ raw payload.
def _matched_display_name(resolution: EntityResolutionResult) -> str:
    for value in resolution.dispatch_payload.values():
        display_name = getattr(value, "name", None)
        if isinstance(display_name, str):
            return display_name
    return "none"


# Ghi debug log sau khi context đã được commit vào store.
def _trace_context_saved(context: BookingContext) -> None:
    trace_log(
        logger,
        logging.INFO,
        "[8] CONTEXT SAVE",
        "saved",
        caller="ConversationContextStore.save()",
        snapshot=_context_log_snapshot(context),
    )


# Log snapshot context đã load để turn hiện tại dùng làm đầu vào tích lũy.
def _trace_context_loaded(context: BookingContext) -> None:
    trace_log(
        logger,
        logging.INFO,
        "[2] CONTEXT",
        "loaded",
        caller="ConversationContextStore.get_copy()",
        snapshot=_context_log_snapshot(context),
    )


# Chỉ log snapshot ngắn gọn phục vụ đọc flow, không dump toàn bộ object nội bộ.
def _context_log_snapshot(context: BookingContext) -> dict[str, object]:
    therapist = context.therapist_preference
    therapist_summary: str | None = None
    if therapist is not None:
        therapist_summary = therapist.therapist_name or therapist.preference_type.value
    available_slots = context.available_slots or ()
    snapshot: dict[str, object] = {
        "state": context.state.value,
        "shop": context.shop.name if context.shop is not None else None,
        "booking_date": context.booking_date.isoformat() if context.booking_date else None,
        "start_time": (
            context.start_time.isoformat(timespec="minutes") if context.start_time else None
        ),
        "num_customer": context.num_customer,
        "duration_minutes": context.duration_minutes,
        "main_course": context.main_course.name if context.main_course is not None else None,
        "addons": [item.name for item in context.addons],
        "course_selection_mode": context.course_selection_mode.value,
        "therapist": therapist_summary,
        "phone_confirmed": context.phone_confirmed,
        "ng_list_status": context.ng_list_status,
        "available_slot_count": len(available_slots),
        "requested_shop_name": context.requested_shop_name,
        "requested_booking_date": (
            context.requested_booking_date.isoformat()
            if context.requested_booking_date is not None
            else None
        ),
        "requested_start_time": (
            context.requested_start_time.isoformat(timespec="minutes")
            if context.requested_start_time is not None
            else None
        ),
        "requested_num_customer": context.requested_num_customer,
        "requested_duration_minutes": context.requested_duration_minutes,
        "requested_main_course_name": context.requested_main_course_name,
        "requested_addon_name": context.requested_addon_name,
        "requested_skip_addon": context.requested_skip_addon,
        "requested_therapist_name": context.requested_therapist_name,
        "requested_therapist_gender": context.requested_therapist_gender,
        "last_failure_code": context.last_failure_code,
    }
    return {
        key: value
        for key, value in snapshot.items()
        if not (
            value is None
            or value is False
            or value == ()
            or value == []
        )
    }


# Tự tải gợi ý an toàn cho state mới để người dùng không phải hỏi danh sách thủ công.
async def _with_proactive_suggestions(
    *,
    response: DialogResponse,
    container: ApplicationContainer,
    context: BookingContext,
) -> DialogResponse:
    # Tải các lựa chọn an toàn cho state mà khách hàng vừa đi vào.
    from app.dialog.instruction_builder import DialogResponse

    try:
        if context.state is BookingState.SELECTING_SHOP:
            shops = list(context.suggested_shops)
            if not context.suggested_shops_loaded:
                shop_handler = cast(SearchShopHandler, container.handler(SearchShopHandler))
                result = await shop_handler.execute(criteria=_shop_search_criteria(context))
                if result.outcome is HandlerOutcome.NOT_FOUND:
                    context.last_failure_code = result.error_code
                    return _shop_not_found_response(
                        context,
                        result.error_code,
                        filtered=False,
                    )
                shops = _handler_items(result, "shops", Shop)
            return _shop_catalog_response(context, shops, filtered=False)

        if context.state is BookingState.SELECTING_SERVICE and context.shop is not None:
            course_type = (
                CourseType.ADDON
                if context.course_selection_mode is CourseSelectionMode.ADDON
                else CourseType.MAIN
            )
            service_handler = cast(
                SearchCourseHandler,
                container.handler(SearchCourseHandler),
            )
            result = await service_handler.execute(
                context.shop.shop_id,
                course_type=course_type,
            )
            courses = _handler_items(result, "courses", Course)
            if course_type is CourseType.MAIN and context.duration_minutes is not None:
                courses = [
                    service
                    for service in courses
                    if service.duration_minutes == context.duration_minutes
                ]
            return _service_step_response(
                context,
                courses,
                course_type=course_type,
            )

        if context.state is BookingState.SELECTING_THERAPIST and context.num_customer == 1:
            therapists = await _available_therapists(container, context)
            names = tuple(
                item.therapist_name for item in therapists[:8] if item.therapist_name is not None
            )
            if names:
                return DialogResponse(
                    text=(
                        "Kỹ thuật viên đang phù hợp với khung giờ đã chọn:\n"
                        + "\n".join(f"{index}. {name}" for index, name in enumerate(names, 1))
                        + "\nBạn có thể chọn theo tên, giới tính hoặc không yêu cầu."
                    ),
                    instruction_template=response.instruction_template,
                    state=context.state,
                    status=response.status,
                    quick_replies=names + ("Không yêu cầu", "Nam", "Nữ"),
                    metadata=response.metadata,
                )
    except Exception as error:
        trace_log(
            logger,
            logging.WARNING,
            "Handler",
            "suggestions_failed",
            state=context.state.value,
            error_code=type(error).__name__,
        )
    return response


# Gọi POS lấy therapist còn trống cho slot đã chọn, chỉ dùng khi single booking.
async def _available_therapists(
    container: ApplicationContainer,
    context: BookingContext,
) -> list[TherapistPreference]:
    if (
        context.shop is None
        or context.booking_date is None
        or context.start_time is None
        or context.total_duration_minutes is None
    ):
        return []
    end_time = (
        datetime.combine(context.booking_date, context.start_time)
        + timedelta(minutes=context.total_duration_minutes)
    ).time()
    gateway = cast(TherapistAvailabilityGateway, container.booking_gateway)
    return await gateway.search_available_therapists(
        AvailableTherapistRequest(
            shop_id=context.shop.shop_id,
            booking_date=context.booking_date,
            start_time=context.start_time,
            end_time=end_time,
        )
    )


# Log metadata instruction an toàn; nội dung đầy đủ chỉ bật trong local debug.
def _log_instruction(response: DialogResponse) -> None:
    trace_log(
        logger,
        logging.DEBUG,
        "InstructionBuilder",
        "instruction_built",
        instruction_template=response.instruction_template or "none",
        instruction_length=len(response.text),
        template_key=response.instruction_template or "none",
    )
    if _local_debug_enabled("LOG_LLM_PROMPTS"):
        trace_log(
            logger,
            logging.DEBUG,
            "DialogCtrl",
            "instruction_content",
            instruction=response.text,
        )


# Chỉ cho phép log raw/debug khi môi trường local và flag tương ứng bật.
def _local_debug_enabled(name: str) -> bool:
    environment = os.getenv("APP_ENV", "production").strip().casefold()
    enabled = os.getenv(name, "false").strip().casefold()
    return environment in {"local", "development", "dev"} and enabled in {
        "true",
        "1",
        "yes",
        "on",
    }


_DISCOVERY_INTENTS = frozenset(
    {
        "list_shops",
        "search_shops",
        "list_services",
        "list_addons",
        "list_available_times",
        "list_therapists",
    }
)


# Xử lý các intent liệt kê/tìm kiếm catalog mà không chọn entity vào booking.
async def _handle_discovery(
    *,
    nlu_result: NLUResult,
    container: ApplicationContainer,
    context: BookingContext,
) -> DialogResponse:
    # Chạy một thao tác catalog chỉ đọc mà không chọn thực thể cụ thể.
    try:
        if nlu_result.intent in {"list_shops", "search_shops"}:
            query = nlu_result.payload.get("location_query")
            if query is not None and not isinstance(query, str):
                return _handled_response(context, "Vui lòng nhập lại khu vực cần tìm.")
            shop_handler = cast(SearchShopHandler, container.handler(SearchShopHandler))
            result = await shop_handler.execute(
                query,
                criteria=_shop_search_criteria(context),
            )
            shops = _handler_items(result, "shops", Shop, allow_not_found=True)
            if not shops and result.outcome is HandlerOutcome.NOT_FOUND:
                context.last_failure_code = result.error_code
                return _shop_not_found_response(
                    context,
                    result.error_code,
                    filtered=query is not None,
                )
            if shops and context.state is BookingState.IDLE:
                context.enter_shop_selection()
            return _shop_catalog_response(context, shops, filtered=query is not None)

        if nlu_result.intent in {"list_services", "list_addons"}:
            if context.shop is None:
                return _handled_response(
                    context,
                    "Bạn hãy chọn cửa hàng trước để tôi tải danh sách liệu trình từ POS.",
                )
            course_type = (
                CourseType.ADDON if nlu_result.intent == "list_addons" else CourseType.MAIN
            )
            service_handler = cast(
                SearchCourseHandler,
                container.handler(SearchCourseHandler),
            )
            result = await service_handler.execute(
                context.shop.shop_id,
                course_type=course_type,
            )
            courses = _handler_items(
                result,
                "courses",
                Course,
                allow_not_found=True,
            )
            if context.duration_minutes is not None:
                courses = [
                    service
                    for service in courses
                    if course_type is CourseType.ADDON
                    or service.duration_minutes == context.duration_minutes
                ]
            return _service_catalog_response(context, courses)

        if nlu_result.intent == "list_available_times":
            missing = _missing_availability_field(context)
            if missing is not None:
                return _handled_response(context, missing)
            availability_handler = cast(
                CheckAvailabilityHandler,
                container.handler(CheckAvailabilityHandler),
            )
            result = await availability_handler.execute(context)
            if result.outcome is HandlerOutcome.NO_SLOTS:
                context.last_failure_code = result.error_code
                context.last_unavailable_date = context.booking_date
                context.change_booking_date(context.booking_date)
                if result.error_code == "no_working_shift":
                    if context.shop is not None and context.booking_date is not None:
                        return _handled_response(
                            context,
                            (
                                f"{context.shop.name} hiện chưa phục vụ đặt lịch vào ngày "
                                f"{context.booking_date.strftime('%d/%m/%Y')}."
                                " Vui lòng chọn ngày khác."
                            ),
                        )
                    return _handled_response(
                        context,
                        "Ngày đã chọn hiện chưa có lịch phục vụ. Vui lòng chọn ngày khác.",
                    )
                if result.error_code == "no_slots_available":
                    return _handled_response(
                        context,
                        "Ngày đã chọn hiện không còn khung giờ trống. Vui lòng chọn ngày khác.",
                    )
                raise RuntimeError(result.error_code or result.outcome.value)
            slots = _handler_items(result, "slots", clock_time)
            context.set_available_slots(tuple(slots))
            context.enter_time_selection()
            context.last_failure_code = None
            context.last_unavailable_date = None
            labels = tuple(slot.strftime("%H:%M") for slot in slots)
            return _catalog_response(
                context,
                "Các khung giờ đang trống: " + ", ".join(labels) + ". Bạn muốn chọn giờ nào?",
                labels,
                len(labels),
            )

        if nlu_result.intent == "list_therapists":
            if context.num_customer is not None and context.num_customer >= 2:
                return _handled_response(
                    context,
                    "Đặt lịch nhóm không hỗ trợ chọn kỹ thuật viên cá nhân.",
                )
            return _handled_response(
                context,
                "POS hiện chưa cung cấp API danh sách kỹ thuật viên cho chatbot.",
            )
    except Exception as error:
        trace_log(
            logger,
            logging.WARNING,
            "Handler",
            "discovery_failed",
            action=nlu_result.intent or "unknown",
            error_code=type(error).__name__,
        )
        context.last_failure_code = type(error).__name__
        return _handled_response(
            context,
            "Hệ thống chưa thể tải danh sách từ POS lúc này. Vui lòng thử lại.",
        )
    return _handled_response(context, "Yêu cầu danh sách chưa được hỗ trợ.")


# Render danh sách shop gợi ý từ POS mà không tự chọn shop thay người dùng.
def _shop_catalog_response(
    context: BookingContext,
    shops: list[Shop],
    *,
    filtered: bool,
) -> DialogResponse:
    if not shops:
        message = (
            "Không tìm thấy cửa hàng trong khu vực này. Vui lòng thử tên khu vực khác."
            if filtered
            else "POS hiện không trả về cửa hàng nào."
        )
        return _handled_response(context, message)
    names = tuple(shop.name for shop in shops)
    lines = "\n".join(f"{index}. {name}" for index, name in enumerate(names, 1))
    # Không thêm hậu tố đếm kết quả vì response hiện hiển thị toàn bộ danh sách đã nhận.
    text = f"Komorebi hiện có các cửa hàng:\n{lines}\nBạn muốn chọn cửa hàng nào?"
    return _catalog_response(context, text, names, len(names))


# Gom requested/confirmed field an toàn để filter shop mà không tự commit booking data.
def _shop_search_criteria(context: BookingContext) -> ShopSearchCriteria:
    return ShopSearchCriteria(
        booking_date=context.requested_booking_date or context.booking_date,
        requested_start_time=context.requested_start_time or context.start_time,
        num_customer=context.requested_num_customer or context.num_customer,
        duration_minutes=context.requested_duration_minutes or context.duration_minutes,
        requested_main_course_name=context.requested_main_course_name,
        requested_addon_name=context.requested_addon_name,
        requested_therapist_name=context.requested_therapist_name,
        requested_therapist_gender=context.requested_therapist_gender,
    )


# Trả thông báo business khi không còn shop phù hợp với constraint đã biết.
def _shop_not_found_response(
    context: BookingContext,
    error_code: str | None,
    *,
    filtered: bool,
) -> DialogResponse:
    if error_code == "service_not_supported_in_any_shop" and context.requested_main_course_name:
        return _handled_response(
            context,
            f"Hiện chưa có cửa hàng nào cung cấp liệu trình {context.requested_main_course_name}.",
        )
    if error_code == "addon_not_supported_in_any_shop" and context.requested_addon_name:
        return _handled_response(
            context,
            f"Hiện chưa có cửa hàng nào hỗ trợ add-on {context.requested_addon_name}.",
        )
    if error_code == "therapist_not_supported_in_any_shop" and context.requested_therapist_name:
        return _handled_response(
            context,
            (
                "Hiện chưa tìm thấy cửa hàng nào có kỹ thuật viên "
                f"{context.requested_therapist_name}. "
                "Bạn có muốn đổi kỹ thuật viên hoặc xem toàn bộ cửa hàng không?"
            ),
        )
    if (
        error_code == "therapist_gender_not_supported_in_any_shop"
        and context.requested_therapist_gender
    ):
        return _handled_response(
            context,
            "Hiện chưa tìm thấy cửa hàng nào có kỹ thuật viên đúng giới tính bạn yêu cầu.",
        )
    if (
        error_code == "requested_shop_time_not_available"
        and context.requested_start_time is not None
    ):
        return _handled_response(
            context,
            (
                f"Hiện chưa có cửa hàng nào còn đúng khung giờ "
                f"{context.requested_start_time.strftime('%H:%M')} "
                "với các điều kiện bạn đã cung cấp. "
                "Bạn muốn đổi thời gian hoặc bớt điều kiện trước không?"
            ),
        )
    message = (
        "Không tìm thấy cửa hàng trong khu vực này. Vui lòng thử tên hoặc khu vực khác."
        if filtered
        else "POS hiện không trả về cửa hàng nào."
    )
    return _handled_response(context, message)


# Render danh sách course/add-on đọc từ POS cho intent discovery.
def _service_catalog_response(
    context: BookingContext,
    courses: list[Course],
) -> DialogResponse:
    if not courses:
        return _handled_response(
            context,
            "POS không trả về liệu trình phù hợp với cửa hàng và thời lượng hiện tại.",
        )
    main = [item for item in courses if item.course_type is CourseType.MAIN]
    addons = [item for item in courses if item.course_type is CourseType.ADDON]
    sections: list[str] = []
    if main:
        sections.append("Liệu trình chính:\n" + _numbered_course_names(main))
    if addons:
        sections.append("Add-on:\n" + _numbered_course_names(addons))
    names = tuple(item.name for item in courses[:8])
    text = "\n".join(sections) + "\nBạn muốn chọn liệu trình nào?"
    return _catalog_response(context, text, names, len(courses))


# Render gợi ý theo bước chọn liệu trình chính hoặc add-on trong booking flow.
def _service_step_response(
    context: BookingContext,
    courses: list[Course],
    *,
    course_type: CourseType,
) -> DialogResponse:
    if course_type is CourseType.MAIN:
        if not courses:
            return _handled_response(
                context,
                "POS không có liệu trình chính phù hợp với thời lượng đã chọn.",
            )
        visible = courses[:8]
        text = (
            "Các liệu trình chính phù hợp:\n"
            + _numbered_course_names(visible)
            + "\nBạn hãy chọn một liệu trình chính."
        )
        return _catalog_response(
            context,
            text,
            tuple(service.name for service in visible),
            len(courses),
        )

    if context.main_course is None:
        raise ValueError("An add-on suggestion requires a selected main course.")
    visible = courses[:7]
    if visible:
        text = (
            f"Liệu trình chính đã chọn: {context.main_course.name}.\n"
            "Các add-on có thể chọn thêm:\n"
            + _numbered_course_names(visible)
            + "\nBạn hãy chọn một add-on hoặc bỏ qua bước này."
        )
    else:
        text = (
            f"Liệu trình chính đã chọn: {context.main_course.name}. "
            "Cửa hàng hiện không có add-on khả dụng; bạn có thể tiếp tục chọn giờ."
        )
    return _catalog_response(
        context,
        text,
        tuple(service.name for service in visible) + ("Không chọn add-on",),
        len(courses),
    )


# Format tên course thành danh sách đánh số ngắn gọn cho response.
def _numbered_course_names(courses: list[Course]) -> str:
    return "\n".join(f"{index}. {service.name}" for index, service in enumerate(courses[:8], 1))


# Tạo DialogResponse cho catalog/listing với quick replies an toàn.
def _catalog_response(
    context: BookingContext,
    text: str,
    quick_replies: tuple[str, ...],
    item_count: int,
) -> DialogResponse:
    from app.dialog.instruction_builder import DialogResponse

    return DialogResponse(
        text=text,
        instruction_template=None,
        state=context.state,
        status=DialogTurnStatus.SUCCESS,
        quick_replies=quick_replies,
        metadata={"item_count": item_count, "quick_reply_limit": len(quick_replies)},
    )


# Xác định field còn thiếu trước khi được phép gọi availability POS.
def _missing_availability_field(context: BookingContext) -> str | None:
    required_fields = (
        (context.shop, "Bạn hãy chọn cửa hàng trước khi xem giờ trống."),
        (context.booking_date, "Bạn hãy chọn ngày trước khi xem giờ trống."),
        (context.num_customer, "Bạn hãy chọn số người trước khi xem giờ trống."),
        (context.duration_minutes, "Bạn hãy chọn thời lượng trước khi xem giờ trống."),
        (context.main_course, "Bạn hãy chọn liệu trình trước khi xem giờ trống."),
    )
    return next((message for value, message in required_fields if value is None), None)


# Render kết quả entity resolution không dispatch được: ambiguous/not_found/unsupported/failure.
async def _entity_response(
    context: BookingContext,
    result: EntityResolutionResult,
    container: ApplicationContainer,
) -> DialogResponse:
    if result.status is EntityResolutionStatus.AMBIGUOUS:
        return _handled_response(
            context,
            _AMBIGUOUS_TEXT[result.entity_kind],
            _candidate_names(result),
        )
    if result.status is EntityResolutionStatus.NOT_FOUND:
        if result.entity_kind is NLUEntityKind.COURSE and context.shop is not None:
            handler = cast(SearchCourseHandler, container.handler(SearchCourseHandler))
            course_type = (
                CourseType.ADDON
                if context.course_selection_mode is CourseSelectionMode.ADDON
                else CourseType.MAIN
            )
            handler_result = await handler.execute(
                context.shop.shop_id,
                course_type=course_type,
            )
            courses = _handler_items(
                handler_result,
                "courses",
                Course,
                allow_not_found=True,
            )
            if course_type is CourseType.MAIN and context.duration_minutes is not None:
                courses = [
                    service
                    for service in courses
                    if service.duration_minutes == context.duration_minutes
                ]
            if courses:
                noun = "add-on" if course_type is CourseType.ADDON else "liệu trình chính"
                visible = courses[:8]
                return _handled_response(
                    context,
                    f"Không tìm thấy {noun} phù hợp. Bạn có thể chọn:\n"
                    + _numbered_course_names(visible),
                    tuple(service.name for service in visible),
                )
        return _handled_response(context, _NOT_FOUND_TEXT[result.entity_kind])
    if result.status is EntityResolutionStatus.UNSUPPORTED:
        return _handled_response(context, _UNSUPPORTED_TEXT[result.entity_kind])
    return _handled_response(context, _ENTITY_FAILURE_TEXT)


# Retry availability từ POS khi người dùng hỏi lại sau lỗi slot/reload.
async def _retry_availability(
    *, container: ApplicationContainer, context: BookingContext
) -> DialogResponse:
    # Recovery fallback: tải lại availability khi state đã có đủ dữ liệu,
    # chưa phải transition chính của flow.
    try:
        missing = _missing_availability_field(context)
        if missing is not None:
            return _handled_response(context, missing)
        handler = cast(
            CheckAvailabilityHandler,
            container.handler(CheckAvailabilityHandler),
        )
        result = await handler.execute(context)
        if result.outcome is HandlerOutcome.NO_SLOTS:
            context.last_failure_code = result.error_code
            context.last_unavailable_date = context.booking_date
            context.change_booking_date(context.booking_date)
            if result.error_code == "no_working_shift":
                if context.shop is not None and context.booking_date is not None:
                    return _handled_response(
                        context,
                        (
                            f"{context.shop.name} hiện chưa phục vụ đặt lịch vào ngày "
                            f"{context.booking_date.strftime('%d/%m/%Y')}. "
                            "Vui lòng chọn ngày khác."
                        ),
                    )
                return _handled_response(
                    context,
                    "Ngày đã chọn hiện chưa có lịch phục vụ. Vui lòng chọn ngày khác.",
                )
            if result.error_code == "no_slots_available":
                return _handled_response(
                    context,
                    "Ngày đã chọn hiện không còn khung giờ trống. Vui lòng chọn ngày khác.",
                )
            raise RuntimeError(result.error_code or result.outcome.value)
        slots = _handler_items(result, "slots", clock_time)
        context.set_available_slots(tuple(slots))
        context.enter_time_selection()
        context.last_failure_code = None
        context.last_unavailable_date = None
        labels = tuple(slot.strftime("%H:%M") for slot in slots)
        return _catalog_response(
            context,
            "Đã tải lại các khung giờ trống: " + ", ".join(labels) + ".",
            labels,
            len(labels),
        )
    except Exception as error:
        context.last_failure_code = type(error).__name__
        return _handled_response(
            context,
            "Tôi vẫn chưa tải được khung giờ từ POS. Các thông tin đã chọn "
            "vẫn được giữ; bạn có thể thử lại hoặc bỏ add-on.",
            ("Thử lại", "Không chọn add-on"),
        )


# Tạo response an toàn cho intent toàn cục như greeting, thanks hoặc repeat question.
def _global_intent_response(intent: str, context: BookingContext) -> DialogResponse:
    from app.dialog.instruction_builder import DialogResponse

    if intent == "greeting":
        if context.has_meaningful_booking_progress():
            text = (
                "Xin chào! Thông tin đặt lịch hiện tại của bạn vẫn được giữ. "
                "Bạn vui lòng cung cấp thêm thông tin còn thiếu để tiếp tục nhé."
            )
        else:
            text = "Xin chào! Mình có thể giúp bạn đặt lịch hoặc giải đáp thông tin dịch vụ."
    elif intent == "thanks":
        text = "Rất vui được hỗ trợ bạn."
    elif intent == "restart_booking":
        text = "Mình đã bắt đầu lại. Bạn hãy chọn cửa hàng."
    else:
        prompt = _UNRESOLVED_TEXT.get(context.state, _DEFAULT_UNRESOLVED_TEXT)
        if context.last_failure_code in {
            "slot_api_error",
            "no_slots_available",
            "no_working_shift",
        }:
            text = (
                "Hiện tại tôi chưa tải được khung giờ từ POS. Thông tin cửa hàng, ngày, "
                "số người và liệu trình vẫn được giữ. Bạn có thể thử lại hoặc chọn liệu trình khác."
            )
        else:
            text = f"Bước hiện tại: {prompt}"
    return DialogResponse(
        text=text,
        instruction_template=None,
        state=context.state,
        status=DialogTurnStatus.SUCCESS,
    )


# Lấy tối đa 8 tên candidate duy nhất để làm quick replies.
def _candidate_names(result: EntityResolutionResult) -> tuple[str, ...]:
    names: list[str] = []
    seen: set[str] = set()
    for candidate in result.candidates:
        if candidate.display_name not in seen:
            seen.add(candidate.display_name)
            names.append(candidate.display_name)
            if len(names) == 8:
                break
    return tuple(names)


# Tạo response recovery an toàn khi turn không dispatch được hoặc business failure đã xử lý.
def _handled_response(
    context: BookingContext,
    text: str,
    quick_replies: tuple[str, ...] = (),
) -> DialogResponse:
    from app.dialog.instruction_builder import DialogResponse

    return DialogResponse(
        text=text,
        instruction_template=None,
        state=context.state,
        status=DialogTurnStatus.FAILURE_HANDLED,
        quick_replies=quick_replies or _state_recovery_quick_replies(context),
    )


# Gắn quick replies theo state hiện tại vào response recovery.
def _with_state_recovery_suggestions(
    response: DialogResponse,
    context: BookingContext,
) -> DialogResponse:
    # Bổ sung quick replies an toàn mà không ghi đè phần giải thích lỗi.
    from app.dialog.instruction_builder import DialogResponse

    return DialogResponse(
        text=response.text,
        instruction_template=response.instruction_template,
        state=response.state,
        status=response.status,
        quick_replies=_state_recovery_quick_replies(context),
        metadata=response.metadata,
    )


# Sinh quick replies dựa trên state và dữ liệu context đã validate.
def _state_recovery_quick_replies(context: BookingContext) -> tuple[str, ...]:
    # Sinh các lựa chọn an toàn dựa trên state hiện tại và context đã validate.
    if context.state is BookingState.SELECTING_SHOP:
        names = tuple(shop.name for shop in context.suggested_shops)
        return names or ("Xem danh sách cửa hàng",)
    if context.state is BookingState.SELECTING_DATE:
        return _date_recovery_quick_replies(context)
    if context.state is BookingState.SELECTING_SERVICE:
        if context.main_course is not None:
            return ("Không chọn add-on", "Xem danh sách add-on")
        return ("Xem danh sách liệu trình",)
    if context.state is BookingState.SELECTING_TIME:
        return tuple(slot.strftime("%H:%M") for slot in (context.available_slots or ()))
    return _RECOVERY_QUICK_REPLIES.get(context.state, ())


def _date_recovery_quick_replies(context: BookingContext) -> tuple[str, ...]:
    failed_date = context.last_unavailable_date
    if failed_date is None:
        return _RECOVERY_QUICK_REPLIES[BookingState.SELECTING_DATE]
    anchor = max(date.today(), failed_date)
    suggestions: list[str] = []
    offset = 1
    while len(suggestions) < 2 and offset <= 14:
        candidate = anchor + timedelta(days=offset)
        if candidate != failed_date:
            suggestions.append(candidate.strftime("%d/%m/%Y"))
        offset += 1
    suggestions.append("Chọn ngày khác")
    return tuple(suggestions)


def _should_resume_recovery(context: BookingContext) -> bool:
    return (
        context.last_unavailable_date is not None
        and context.shop is not None
        and context.num_customer is not None
        and context.duration_minutes is not None
        and context.main_course is not None
    )




# Tạo menu chọn field cần sửa khi người dùng chỉ nói muốn chỉnh sửa booking.
def _change_menu_response(context: BookingContext) -> DialogResponse:
    from app.dialog.instruction_builder import DialogResponse

    return DialogResponse(
        text=(
            "Bạn muốn chỉnh sửa thông tin nào? Việc chỉnh sửa sẽ không tạo booking "
            "cho đến khi bạn xác nhận lại."
        ),
        instruction_template=None,
        state=context.state,
        status=DialogTurnStatus.SUCCESS,
        quick_replies=(
            "Đổi cửa hàng",
            "Đổi ngày",
            "Đổi số người",
            "Đổi thời lượng",
            "Đổi liệu trình",
            "Đổi giờ",
            "Đổi kỹ thuật viên",
            "Đổi số điện thoại",
        ),
        metadata={"can_change_info": True},
    )


# Lấy danh sách item typed từ HandlerResult cho các path discovery/retry.
def _handler_items(
    result: HandlerResult,
    key: str,
    item_type: type[T],
    *,
    allow_not_found: bool = False,
) -> list[T]:
    if allow_not_found and result.outcome is HandlerOutcome.NOT_FOUND:
        return []
    if result.outcome not in {HandlerOutcome.SUCCESS, HandlerOutcome.AMBIGUOUS}:
        raise RuntimeError(result.error_code or result.outcome.value)
    value = result.data.get(key)
    if not isinstance(value, tuple) or any(not isinstance(item, item_type) for item in value):
        raise RuntimeError(f"Handler result '{key}' is invalid.")
    return list(value)
