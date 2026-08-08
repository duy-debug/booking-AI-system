"""Registry and sequential executor for declarative dialog actions."""

import logging
import re
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, fields
from datetime import date, time
from functools import partial
from time import perf_counter
from typing import Protocol, TypeAlias, TypeVar

from app.application.handlers.check_availability_handler import (
    CheckAvailabilityHandler,
)
from app.application.handlers.check_customer_handler import CheckCustomerHandler
from app.application.handlers.create_booking_handler import CreateBookingHandler
from app.application.handlers.search_shop_handler import SearchShopHandler
from app.application.handlers.select_booking_info_handler import SelectBookingInfoHandler
from app.application.handlers.select_schedule_handler import SelectScheduleHandler
from app.dialog.flow_loader import (
    FlowFailure,
    InvalidFlowConditionError,
)
from app.domain.booking_context import BookingContext
from app.domain.booking_models import (
    BookingConflictError,
    BookingContextNotReadyError,
    BookingRules,
    CourseSelection,
    Customer,
    CustomerNotAllowedError,
    CustomerVerificationMismatchError,
    CustomerVerificationRequiredError,
    InvalidBookingDataError,
    InvalidCourseSelectionError,
    InvalidDurationError,
    InvalidIdempotencyKeyError,
    PhoneNotConfirmedError,
    Shop,
    ShopSearchCriteria,
    SlotConflictError,
    TherapistNotAllowedForGroupError,
    TherapistPreference,
    TherapistPreferenceType,
)
from app.domain.outcomes import HandlerOutcome, HandlerResult
from app.infrastructure.context_store import elapsed_ms, trace_log

_ACTION_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
_EXTERNAL_SIDE_EFFECT_ACTIONS = frozenset({"create_booking"})
T = TypeVar("T")


@dataclass(slots=True)
class ActionExecutionContext:
    """Contains parsed input and mutable booking data for one action execution."""

    booking_context: BookingContext
    intent: str
    payload: Mapping[str, object]
    idempotency_key: str | None = None


@dataclass(frozen=True, slots=True)
class ActionResult:
    """Contains the output produced by one successful action."""

    action_name: str
    output: object | None = None


@dataclass(frozen=True, slots=True)
class ActionExecutionReport:
    """Contains results from a successfully completed action sequence."""

    results: tuple[ActionResult, ...]

    @property
    def succeeded(self) -> bool:
        """Return whether the action sequence completed successfully."""
        return True

    @property
    def executed_action_names(self) -> tuple[str, ...]:
        """Return successful action names in execution order."""
        return tuple(result.action_name for result in self.results)


class FailureCodeProvider(Protocol):
    """Maps a root exception to a stable public failure code."""

    def __call__(self, error: Exception) -> str:
        """Return a stable snake_case failure code."""
        ...


ActionCallable: TypeAlias = Callable[
    [ActionExecutionContext],
    Awaitable[ActionResult],
]


class ActionRegistryError(Exception):
    """Base exception for action registry and execution failures."""


class DuplicateActionError(ActionRegistryError):
    """Raised when an action name is registered more than once."""


class UnknownActionError(ActionRegistryError):
    """Raised when an action name has no registered callable."""


class InvalidActionNameError(ActionRegistryError):
    """Raised when an action name does not follow the registry naming contract."""


class InvalidActionSequenceError(ActionRegistryError):
    """Raised when external side-effect actions are ordered unsafely."""


class InvalidActionInputError(ActionRegistryError):
    """Raised when an action is missing typed input required for execution."""


class ActionExecutionError(ActionRegistryError):
    """Wrap an exception raised while executing a registered action."""

    def __init__(
        self,
        action_name: str,
        executed_actions: tuple[str, ...],
        cause: Exception,
    ) -> None:
        self.action_name = action_name
        self.executed_actions = executed_actions
        self.cause = cause
        super().__init__(f"Action '{action_name}' failed: {cause}")


@dataclass(frozen=True, slots=True)
class FailureDescriptor:
    """Describes a mapped action failure without changing dialog state."""

    code: str
    action_name: str
    cause: Exception


# Lấy payload bắt buộc cho action và fail fast nếu kiểu dữ liệu không đúng contract.
def _require_payload_value(
    context: ActionExecutionContext,
    key: str,
    expected_type: type[T],
) -> T:
    if key not in context.payload:
        raise InvalidActionInputError(f"Action '{context.intent}' requires payload key '{key}'.")

    value = context.payload[key]
    invalid_bool = expected_type is int and isinstance(value, bool)
    if value is None or not isinstance(value, expected_type) or invalid_bool:
        raise InvalidActionInputError(
            f"Action '{context.intent}' requires '{key}' to be {expected_type.__name__}."
        )
    return value


class ActionRegistry:
    """Registers explicit action bindings and executes them sequentially."""

    # Đăng ký action declarative và handler thật được inject từ composition root.
    def __init__(
        self,
        *,
        search_shop_handler: SearchShopHandler | None = None,
        check_availability_handler: CheckAvailabilityHandler | None = None,
        create_booking_handler: CreateBookingHandler | None = None,
        select_booking_info_handler: SelectBookingInfoHandler | None = None,
        select_schedule_handler: SelectScheduleHandler | None = None,
        check_customer_handler: CheckCustomerHandler | None = None,
        failure_code_provider: FailureCodeProvider | None = None,
    ) -> None:
        self._actions: dict[str, ActionCallable] = {}
        self._search_shop_handler = search_shop_handler
        self._check_availability_handler = check_availability_handler
        self._create_booking_handler = create_booking_handler
        self._select_booking_info_handler = select_booking_info_handler
        self._select_schedule_handler = select_schedule_handler
        self._check_customer_handler = check_customer_handler
        self._failure_code_provider = failure_code_provider
        self._register_domain_actions()
        self._register_injected_handler_actions()

    # Đăng ký binding action theo tên trong flow JSON mà không cho ghi đè âm thầm.
    def register_action(self, name: str, action: ActionCallable) -> None:
        """Register an explicitly supplied async action without overriding."""
        normalized_name = self._normalize_action_name(name)
        if not callable(action):
            raise TypeError("Action must be callable.")
        if normalized_name in self._actions:
            raise DuplicateActionError(f"Action '{normalized_name}' is already registered.")
        self._actions[normalized_name] = action

    def has_action(self, name: str) -> bool:
        """Return whether an action name is registered."""
        return isinstance(name, str) and name.strip() in self._actions

    def registered_actions(self) -> tuple[str, ...]:
        """Return registered names in insertion order."""
        return tuple(self._actions)

    def get_action(self, name: str) -> ActionCallable:
        """Return a registered action or raise for an unknown name."""
        normalized_name = name.strip()
        try:
            return self._actions[normalized_name]
        except KeyError as error:
            raise UnknownActionError(f"Action '{normalized_name}' is not registered.") from error

    def find_unregistered_actions(
        self,
        declared_actions: Iterable[str],
    ) -> tuple[str, ...]:
        """Return unique unregistered declarations in first-seen order."""
        seen: set[str] = set()
        missing: list[str] = []
        for name in declared_actions:
            if name not in seen:
                seen.add(name)
                if not self.has_action(name):
                    missing.append(name)
        return tuple(missing)

    def get_failure_code(self, error: ActionExecutionError) -> str:
        """Map an action execution failure to a stable public code."""
        cause = self._unwrap_action_error(error)
        if self._failure_code_provider is not None:
            code = self._failure_code_provider(cause)
            if not _ACTION_NAME_PATTERN.fullmatch(code):
                raise InvalidActionInputError(
                    "Failure code provider must return a snake_case identifier."
                )
            return code
        return self._default_failure_code(error.action_name, cause)

    def describe_failure(self, error: ActionExecutionError) -> FailureDescriptor:
        """Return mapped failure metadata while preserving the original error."""
        return FailureDescriptor(
            code=self.get_failure_code(error),
            action_name=error.action_name,
            cause=self._unwrap_action_error(error),
        )

    def mapped_failure_codes(self) -> tuple[str, ...]:
        """Return all stable codes the default mapper can produce."""
        return (
            "invalid_phone",
            "booking_data_incomplete",
            "customer_ng_blocked",
            "combo_not_bookable",
            "duration_not_multiple_15",
            "course_duration_mismatch",
            "therapist_unavailable",
            "booking_conflict",
            "customer_verification_mismatch",
            "unknown_action_error",
            "action_sequence_invalid",
            "flow_configuration_error",
            "slot_api_error",
            "booking_api_error",
            "action_execution_error",
        )

    # Chạy recovery actions nhưng chặn mọi side effect có thể tạo booking lại.
    async def execute_failure_actions(
        self,
        failure: FlowFailure,
        context: ActionExecutionContext,
    ) -> ActionExecutionReport:
        """Execute recovery actions without applying the failure target."""
        forbidden = tuple(
            action for action in failure.actions if action in _EXTERNAL_SIDE_EFFECT_ACTIONS
        )
        if forbidden:
            raise InvalidActionSequenceError("Failure actions must not create or retry a booking.")
        return await self.execute_actions(failure.actions, context)

    # Chạy một action đơn lẻ trên snapshot để rollback nếu action lỗi.
    async def execute_action(
        self,
        action_name: str,
        context: ActionExecutionContext,
    ) -> ActionResult:
        """Execute one action and restore local context if it fails."""
        normalized_name = self._normalize_action_name(action_name)
        self._validate_idempotency(normalized_name, context)
        snapshot = self._snapshot_booking_context(context.booking_context)
        try:
            action = self.get_action(normalized_name)
            return await self._invoke_action(normalized_name, action, context)
        except UnknownActionError as error:
            self._restore_booking_context(context.booking_context, snapshot)
            raise ActionExecutionError(normalized_name, (), error) from error
        except ActionExecutionError:
            self._restore_booking_context(context.booking_context, snapshot)
            raise

    # Điều phối chuỗi business action và rollback toàn bộ working context nếu có lỗi.
    async def execute_actions(
        self,
        action_names: Sequence[str],
        context: ActionExecutionContext,
    ) -> ActionExecutionReport:
        """Execute actions in order and roll back local context on failure."""
        names = tuple(self._normalize_action_name(name) for name in action_names)
        self._validate_action_sequence(names)
        for name in names:
            self._validate_idempotency(name, context)

        snapshot = self._snapshot_booking_context(context.booking_context)
        results: list[ActionResult] = []
        try:
            for name in names:
                try:
                    action = self.get_action(name)
                except UnknownActionError as error:
                    raise ActionExecutionError(name, (), error) from error
                results.append(await self._invoke_action(name, action, context))
        except ActionExecutionError as error:
            self._restore_booking_context(context.booking_context, snapshot)
            cause = error.__cause__
            assert isinstance(cause, Exception)
            raise ActionExecutionError(
                action_name=error.action_name,
                executed_actions=tuple(result.action_name for result in results),
                cause=cause,
            ) from cause

        return ActionExecutionReport(tuple(results))

    @staticmethod
    # Chuẩn hóa tên action từ flow để tránh registry nhận tên không an toàn.
    def _normalize_action_name(name: str) -> str:
        if not isinstance(name, str):
            raise InvalidActionNameError("Action name must be a string.")
        normalized_name = name.strip()
        if not _ACTION_NAME_PATTERN.fullmatch(normalized_name):
            raise InvalidActionNameError(
                "Action name must be non-empty snake_case and start with a letter."
            )
        return normalized_name

    @staticmethod
    # Bóc lỗi gốc khỏi ActionExecutionError lồng nhau để map failure code chính xác.
    def _unwrap_action_error(error: Exception) -> Exception:
        current = error
        seen: set[int] = set()
        for _ in range(16):
            if not isinstance(current, ActionExecutionError):
                return current
            if id(current) in seen:
                return current
            seen.add(id(current))
            cause = current.cause
            if cause is current:
                return current
            current = cause
        return current

    @staticmethod
    def _default_failure_code(
        action_name: str,
        error: Exception,
    ) -> str:
        if isinstance(error, UnknownActionError):
            return "unknown_action_error"
        if isinstance(error, InvalidActionSequenceError):
            return "action_sequence_invalid"
        if isinstance(error, InvalidFlowConditionError):
            return "flow_configuration_error"
        if isinstance(error, SlotConflictError | BookingConflictError):
            if action_name == "load_time_slots":
                if isinstance(error, SlotConflictError) and error.reason in {
                    "no_slots_available",
                    "no_working_shift",
                }:
                    return error.reason
                return "no_slots_available"
            if action_name == "handle_time_selection":
                return "slot_unavailable"
            return "booking_conflict"
        if isinstance(error, CustomerVerificationMismatchError):
            return "customer_verification_mismatch"
        if isinstance(error, CustomerNotAllowedError):
            return "customer_ng_blocked"
        if isinstance(error, BookingContextNotReadyError):
            return "booking_data_incomplete"
        if isinstance(
            error,
            (
                PhoneNotConfirmedError,
                CustomerVerificationRequiredError,
                InvalidIdempotencyKeyError,
                InvalidActionInputError,
            ),
        ):
            if action_name in {"handle_phone_collection", "validate_phone"}:
                return "invalid_phone"
            return "booking_data_incomplete"
        if isinstance(error, InvalidDurationError):
            if action_name == "handle_duration_selection":
                return "duration_not_multiple_15"
            return "course_duration_mismatch"
        if isinstance(error, InvalidCourseSelectionError):
            return "combo_not_bookable"
        if isinstance(error, TherapistNotAllowedForGroupError):
            return "therapist_unavailable"
        if isinstance(error, InvalidBookingDataError):
            error_code = str(error)
            if action_name == "handle_people_selection" and error_code in {
                "num_customer_invalid",
                "num_customer_too_many",
            }:
                return error_code
            if action_name == "handle_date_selection" and error_code in {
                "date_in_past",
                "date_still_unavailable",
            }:
                return error_code
            if action_name in {"handle_phone_collection", "validate_phone"}:
                return "invalid_phone"
            return "booking_data_incomplete"
        if action_name == "load_time_slots":
            return "slot_api_error"
        if action_name in {
            "create_booking",
            "handle_phone_collection",
        }:
            return "booking_api_error"
        return "action_execution_error"

    @staticmethod
    def _validate_action_sequence(action_names: tuple[str, ...]) -> None:
        side_effects = tuple(name for name in action_names if name in _EXTERNAL_SIDE_EFFECT_ACTIONS)
        if len(side_effects) > 1:
            raise InvalidActionSequenceError(
                "An action sequence may contain only one booking side effect."
            )
        if side_effects and action_names[-1] != side_effects[0]:
            raise InvalidActionSequenceError(
                f"External side-effect action '{side_effects[0]}' must be last."
            )

    @staticmethod
    def _validate_idempotency(
        action_name: str,
        context: ActionExecutionContext,
    ) -> None:
        if action_name not in _EXTERNAL_SIDE_EFFECT_ACTIONS:
            return
        key = context.idempotency_key
        if key is None or not key.strip():
            raise InvalidActionInputError(
                f"Action '{action_name}' requires a non-empty idempotency key."
            )

    @staticmethod
    async def _invoke_action(
        action_name: str,
        action: ActionCallable,
        context: ActionExecutionContext,
    ) -> ActionResult:
        started_at = perf_counter()
        function_name = getattr(action, "__name__", type(action).__name__)
        before = {
            field.name: deepcopy(getattr(context.booking_context, field.name))
            for field in fields(BookingContext)
        }
        trace_log(
            logging.getLogger(__name__),
            logging.DEBUG,
            function_name,
            "handler_started",
            handler=function_name,
            function=function_name,
            action=action_name,
            input_summary={
                "intent": context.intent,
                "payload_keys": sorted(context.payload),
                "state": context.booking_context.state.value,
            },
            status="started",
        )
        try:
            result = await action(context)
            if not isinstance(result, ActionResult):
                raise TypeError(
                    f"Action '{action_name}' must return ActionResult, not {type(result).__name__}."
                )
            if result.action_name != action_name:
                raise TypeError(
                    f"Action '{action_name}' returned result for '{result.action_name}'."
                )
            trace_log(
                logging.getLogger(__name__),
                logging.INFO,
                function_name,
                "handler_verification_completed",
                handler=function_name,
                verification="passed",
                business_rules_checked=[action_name],
            )
            updated_fields = sorted(
                field.name
                for field in fields(BookingContext)
                if getattr(context.booking_context, field.name) != before[field.name]
            )
            trace_log(
                logging.getLogger(__name__),
                logging.INFO,
                function_name,
                "handler_completed",
                handler=function_name,
                function=function_name,
                action=action_name,
                output_summary=(
                    type(result.output).__name__ if result.output is not None else "none"
                ),
                status="success",
                context_updates=updated_fields,
                duration_ms=elapsed_ms(started_at),
            )
            return result
        except Exception as error:
            trace_log(
                logging.getLogger(__name__),
                logging.WARNING,
                function_name,
                "handler_failed",
                handler=function_name,
                function=function_name,
                action=action_name,
                status="failure",
                error_code=type(error).__name__,
                duration_ms=elapsed_ms(started_at),
            )
            raise ActionExecutionError(action_name, (), error) from error

    @staticmethod
    def _snapshot_booking_context(context: BookingContext) -> BookingContext:
        return deepcopy(context)

    @staticmethod
    def _restore_booking_context(
        target: BookingContext,
        snapshot: BookingContext,
    ) -> None:
        for field in fields(BookingContext):
            setattr(target, field.name, deepcopy(getattr(snapshot, field.name)))

    def _register_domain_actions(self) -> None:
        bindings: tuple[tuple[str, ActionCallable], ...] = (
            ("handle_store_selection", self._handle_store_selection),
            ("handle_date_selection", self._handle_date_selection),
            ("handle_people_selection", self._handle_people_selection),
            ("handle_duration_selection", self._handle_duration_selection),
            ("handle_course_selection", self._handle_course_selection),
            ("skip_addon", self._skip_addon),
            ("handle_time_selection", self._handle_time_selection),
            ("handle_therapist_selection", self._handle_therapist_selection),
            ("change_shop", self._change_shop),
            ("change_date", self._change_date),
            ("change_people", self._change_people),
            ("change_duration", self._change_duration),
            ("change_course", self._change_course),
            ("change_time", self._change_time),
            ("change_therapist", self._change_therapist),
            ("change_phone", self._change_phone),
            ("skip_therapist", self._skip_therapist),
            ("skip_therapist_for_group", self._skip_therapist_for_group),
            ("clear_phone_confirmation", self._clear_phone_confirmation),
            ("validate_phone", self._validate_phone),
            ("handle_customer_name", self._handle_customer_name),
            ("clear_course_for_reselect", self._clear_course_for_reselect),
            ("infer_duration_from_course", self._infer_duration_from_course),
        )
        for name, action in bindings:
            self.register_action(name, action)
        for name in (
            "ask_to_clarify",
            "log_unhandled",
            "defer_change_info",
            "ask_date",
            "no_slots_available",
            "ask_people",
            "people_too_many",
            "handle_booking_failure",
        ):
            self.register_action(
                name,
                partial(self._acknowledge_declarative_action, action_name=name),
            )

    async def _acknowledge_declarative_action(
        self,
        context: ActionExecutionContext,
        *,
        action_name: str,
    ) -> ActionResult:
        """Acknowledge a renderer/state-machine marker with no domain mutation."""
        del context
        return ActionResult(action_name)

    async def _clear_course_for_reselect(self, context: ActionExecutionContext) -> ActionResult:
        context.booking_context.change_course_selection(None)
        return ActionResult("clear_course_for_reselect")

    async def _infer_duration_from_course(self, context: ActionExecutionContext) -> ActionResult:
        booking = context.booking_context
        if booking.duration_minutes is None and booking.main_course is not None:
            booking.set_duration(booking.main_course.duration_minutes)
        return ActionResult("infer_duration_from_course", booking.duration_minutes)

    # Đăng ký các action cần handler thật như POS availability, customer check và create booking.
    def _register_injected_handler_actions(self) -> None:
        if self._search_shop_handler is not None:
            self.register_action("search_shop", self._search_shop)
        if self._check_availability_handler is not None:
            self.register_action("load_time_slots", self._load_time_slots)
            self.register_action(
                "reload_time_slots",
                partial(self._load_time_slots, action_name="reload_time_slots"),
            )
        if self._check_customer_handler is not None:
            self.register_action(
                "handle_phone_collection",
                self._handle_phone_collection,
            )
            self.register_action("mark_phone_confirmed", self._mark_phone_confirmed)
        if self._create_booking_handler is not None:
            self.register_action("create_booking", self._create_booking)

    # Gọi handler tìm danh sách shop và lưu catalog gợi ý vào BookingContext.
    async def _search_shop(
        self,
        context: ActionExecutionContext,
    ) -> ActionResult:
        assert self._search_shop_handler is not None
        requested_date = context.payload.get("booking_date")
        requested_time = context.payload.get("start_time")
        if requested_date is not None and type(requested_date) is not date:
            raise InvalidActionInputError("Requested booking date is invalid.")
        if requested_time is not None and type(requested_time) is not time:
            raise InvalidActionInputError("Requested start time is invalid.")
        context.booking_context.requested_booking_date = requested_date
        context.booking_context.requested_start_time = requested_time
        result = await self._search_shop_handler.execute(
            criteria=_shop_search_criteria(context.booking_context)
        )
        if result.outcome is HandlerOutcome.NOT_FOUND:
            context.booking_context.last_failure_code = result.error_code
            context.booking_context.suggested_shops = ()
            context.booking_context.suggested_shops_loaded = True
            return ActionResult("search_shop", [])
        _ensure_success(result)
        shops = _typed_result_items(result, "shops", Shop)
        context.booking_context.suggested_shops = tuple(shops)
        context.booking_context.suggested_shops_loaded = True
        context.booking_context.last_failure_code = None
        return ActionResult("search_shop", shops)

    # Áp dụng shop đã resolve vào context và clear các dữ liệu phụ thuộc.
    async def _handle_store_selection(
        self,
        context: ActionExecutionContext,
    ) -> ActionResult:
        shop = _require_payload_value(context, "shop", Shop)
        context.booking_context.set_shop(shop)
        return ActionResult("handle_store_selection", shop)

    # Validate và lưu ngày booking đã chọn.
    async def _handle_date_selection(
        self,
        context: ActionExecutionContext,
    ) -> ActionResult:
        booking_date = _require_payload_value(context, "booking_date", date)
        handler = self._select_booking_info_handler
        if handler is None:
            if _should_preserve_recovery_selection(context.booking_context):
                context.booking_context.change_booking_date(booking_date)
            else:
                context.booking_context.set_booking_date(booking_date)
        else:
            result = handler.select_date(context.booking_context, booking_date)
            _ensure_success(result)
            if _should_preserve_recovery_selection(context.booking_context):
                context.booking_context.change_booking_date(booking_date)
            else:
                context.booking_context.set_booking_date(booking_date)
        return ActionResult("handle_date_selection", booking_date)

    # Validate và lưu số người, để domain tự clear therapist/slot khi cần.
    async def _handle_people_selection(
        self,
        context: ActionExecutionContext,
    ) -> ActionResult:
        num_customer = _require_payload_value(context, "num_customer", int)
        handler = self._select_booking_info_handler
        if handler is None:
            context.booking_context.set_num_customer(num_customer)
        else:
            result = handler.select_people(context.booking_context, num_customer)
            _ensure_success(result)
            context.booking_context.set_num_customer(num_customer)
        return ActionResult("handle_people_selection", num_customer)

    # Validate thời lượng trước khi chuyển sang chọn liệu trình.
    async def _handle_duration_selection(
        self,
        context: ActionExecutionContext,
    ) -> ActionResult:
        duration = _require_payload_value(context, "duration_minutes", int)
        handler = self._select_booking_info_handler
        if handler is None:
            context.booking_context.set_duration(duration)
        else:
            result = handler.select_duration(context.booking_context, duration)
            if result.error_code == "duration_not_multiple_15":
                raise InvalidDurationError(result.error_code)
            _ensure_success(result)
            context.booking_context.set_duration(duration)
        return ActionResult("handle_duration_selection", duration)

    # Lưu main course/add-on đã resolve vào BookingContext.
    async def _handle_course_selection(
        self,
        context: ActionExecutionContext,
    ) -> ActionResult:
        selection = _require_payload_value(
            context,
            "course_selection",
            CourseSelection,
        )
        context.booking_context.set_course_selection(selection)
        return ActionResult("handle_course_selection", selection)

    # Đánh dấu người dùng không chọn add-on để flow có thể chuyển bước tiếp.
    async def _skip_addon(self, context: ActionExecutionContext) -> ActionResult:
        context.booking_context.skip_addon()
        return ActionResult("skip_addon", None)

    # Chỉ nhận slot nằm trong latest available_slots đã load từ POS.
    async def _handle_time_selection(
        self,
        context: ActionExecutionContext,
    ) -> ActionResult:
        start_time = _require_payload_value(context, "start_time", time)
        available_slots = context.booking_context.available_slots
        if available_slots is None or start_time not in available_slots:
            raise SlotConflictError(
                nearest_slots=available_slots or (),
                reason="Selected time is not in the latest available slots.",
            )
        handler = self._select_schedule_handler
        if handler is None:
            context.booking_context.set_start_time(start_time)
        else:
            result = handler.select_time(context.booking_context, start_time)
            _ensure_success(result)
            context.booking_context.set_start_time(start_time)
        return ActionResult("handle_time_selection", start_time)

    # Lưu yêu cầu therapist đã được domain/POS xác thực theo chính sách booking.
    async def _handle_therapist_selection(
        self,
        context: ActionExecutionContext,
    ) -> ActionResult:
        preference = _require_payload_value(
            context,
            "therapist_preference",
            TherapistPreference,
        )
        handler = self._select_schedule_handler
        if handler is None:
            context.booking_context.set_therapist_preference(preference)
        else:
            result = handler.select_therapist(context.booking_context, preference)
            if result.error_code == "group_therapist_not_allowed":
                raise TherapistNotAllowedForGroupError(result.error_code)
            _ensure_success(result)
            context.booking_context.set_therapist_preference(preference)
            context.booking_context.set_therapist_verified(True)
        return ActionResult("handle_therapist_selection", preference)

    # Đổi shop và clear các field phụ thuộc để tránh dùng dữ liệu của shop cũ.
    async def _change_shop(self, context: ActionExecutionContext) -> ActionResult:
        shop = context.payload.get("shop")
        if shop is not None and not isinstance(shop, Shop):
            raise InvalidActionInputError("Changed shop must be a Shop.")
        context.booking_context.change_shop(shop)
        return ActionResult("change_shop", shop)

    # Đổi ngày và clear slot/therapist đã phụ thuộc vào ngày cũ.
    async def _change_date(self, context: ActionExecutionContext) -> ActionResult:
        booking_date = context.payload.get("booking_date")
        if booking_date is not None and type(booking_date) is not date:
            raise InvalidActionInputError("Changed booking date must be a date.")
        context.booking_context.change_booking_date(booking_date)
        return ActionResult("change_date", booking_date)

    # Đổi số người và giữ rollback atomic nếu giá trị vượt rule domain.
    async def _change_people(self, context: ActionExecutionContext) -> ActionResult:
        value = context.payload.get("num_customer")
        if value is not None and type(value) is not int:
            raise InvalidActionInputError("Changed customer count must be an integer.")
        context.booking_context.change_num_customer(value)
        return ActionResult("change_people", value)

    # Đổi duration và clear liệu trình/availability đang phụ thuộc duration cũ.
    async def _change_duration(self, context: ActionExecutionContext) -> ActionResult:
        value = context.payload.get("duration_minutes")
        if value is not None and type(value) is not int:
            raise InvalidActionInputError("Changed duration must be an integer.")
        context.booking_context.change_duration(value)
        return ActionResult("change_duration", value)

    # Đổi course hoặc add-on rồi buộc reload slot/time/therapist sau đó.
    async def _change_course(self, context: ActionExecutionContext) -> ActionResult:
        selection = context.payload.get("course_selection")
        if selection is not None and not isinstance(selection, CourseSelection):
            raise InvalidActionInputError("Changed course must be a CourseSelection.")
        context.booking_context.change_course_selection(selection)
        return ActionResult("change_course", selection)

    # Đổi giờ booking và yêu cầu xác thực lại therapist nếu có.
    async def _change_time(self, context: ActionExecutionContext) -> ActionResult:
        start_time = context.payload.get("start_time")
        if start_time is not None and type(start_time) is not time:
            raise InvalidActionInputError("Changed start time must be a time.")
        context.booking_context.change_start_time(start_time)
        return ActionResult("change_time", start_time)

    # Đổi yêu cầu therapist theo giới tính hoặc bỏ yêu cầu, không tạo booking.
    async def _change_therapist(
        self,
        context: ActionExecutionContext,
    ) -> ActionResult:
        gender = context.payload.get("therapist_gender")
        if gender is not None and gender not in {"male", "female", "none"}:
            raise InvalidActionInputError("Changed therapist gender is invalid.")
        preference = (
            None if gender is None else TherapistPreference(TherapistPreferenceType(gender))
        )
        context.booking_context.change_therapist_preference(preference)
        return ActionResult("change_therapist", preference)

    # Đổi số điện thoại và reset trạng thái xác thực khách hàng.
    async def _change_phone(self, context: ActionExecutionContext) -> ActionResult:
        phone = context.payload.get("phone")
        if phone is not None:
            if not isinstance(phone, str):
                raise InvalidActionInputError("Changed phone must be a string.")
            BookingRules.validate_phone(phone)
        context.booking_context.change_phone(phone)
        return ActionResult("change_phone", phone)

    # Lưu lựa chọn không yêu cầu therapist cho booking một người.
    async def _skip_therapist(
        self,
        context: ActionExecutionContext,
    ) -> ActionResult:
        preference = TherapistPreference(TherapistPreferenceType.NONE)
        context.booking_context.set_therapist_preference(preference)
        return ActionResult("skip_therapist", preference)

    # Tự bỏ therapist cá nhân cho group booking vì nhóm chỉ được chọn giới tính/none.
    async def _skip_therapist_for_group(
        self,
        context: ActionExecutionContext,
    ) -> ActionResult:
        if context.booking_context.num_customer not in (2, 3):
            raise InvalidActionInputError(
                "Action 'skip_therapist_for_group' requires two or three customers."
            )
        preference = TherapistPreference(TherapistPreferenceType.NONE)
        handler = self._select_schedule_handler
        if handler is None:
            context.booking_context.set_therapist_preference(preference)
        else:
            result = handler.select_therapist(context.booking_context, preference)
            _ensure_success(result)
            context.booking_context.set_therapist_preference(preference)
            context.booking_context.set_therapist_verified(True)
        return ActionResult("skip_therapist_for_group")

    # Validate format phone trước khi cho phép confirm hoặc check customer.
    async def _validate_phone(
        self,
        context: ActionExecutionContext,
    ) -> ActionResult:
        phone = context.booking_context.phone
        if phone is None:
            raise InvalidActionInputError("Action 'validate_phone' requires a collected phone.")
        BookingRules.validate_phone(phone)
        return ActionResult("validate_phone", phone)

    # Xóa phone đã nhập khi người dùng phủ nhận số điện thoại.
    async def _clear_phone_confirmation(
        self,
        context: ActionExecutionContext,
    ) -> ActionResult:
        context.booking_context.clear_phone()
        return ActionResult("clear_phone_confirmation")

    # Gọi availability handler để lấy slot mới nhất từ POS và lưu vào context.
    async def _load_time_slots(
        self,
        context: ActionExecutionContext,
        *,
        action_name: str = "load_time_slots",
    ) -> ActionResult:
        assert self._check_availability_handler is not None
        result = await self._check_availability_handler.execute(context.booking_context)
        if result.outcome is HandlerOutcome.NO_SLOTS:
            context.booking_context.last_unavailable_date = context.booking_context.booking_date
            raise SlotConflictError(reason=result.error_code)
        _ensure_success(result)
        slots = _typed_result_items(result, "slots", time)
        context.booking_context.set_available_slots(slots)
        context.booking_context.last_unavailable_date = None
        return ActionResult(
            action_name,
            slots,
        )

    # Gọi POS/customer handler để kiểm tra phone, blacklist và trạng thái khách hàng.
    async def _handle_phone_collection(
        self,
        context: ActionExecutionContext,
    ) -> ActionResult:
        assert self._check_customer_handler is not None
        phone = _require_payload_value(context, "phone", str)
        name_value = context.payload.get("name")
        if name_value is not None and not isinstance(name_value, str):
            raise InvalidActionInputError(
                "Action 'handle_phone_collection' requires 'name' to be str."
            )
        result = await self._check_customer_handler.check(
            context.booking_context,
            phone,
            name_value,
        )
        if result.outcome is HandlerOutcome.BLOCKED:
            raise CustomerNotAllowedError(result.error_code)
        if result.error_code == "customer_verification_mismatch":
            raise CustomerVerificationMismatchError(result.error_code)
        _ensure_success(result)
        _apply_context_updates(context.booking_context, result)
        return ActionResult("handle_phone_collection", result.data["verification"])

    # Commit trạng thái phone_confirmed sau khi người dùng xác nhận số điện thoại.
    async def _mark_phone_confirmed(
        self,
        context: ActionExecutionContext,
    ) -> ActionResult:
        assert self._check_customer_handler is not None
        result = self._check_customer_handler.confirm(context.booking_context)
        _ensure_success(result)
        _apply_context_updates(context.booking_context, result)
        return ActionResult("mark_phone_confirmed")

    # Lưu tên cho khách mới sau khi phone chưa có customer record trên POS.
    async def _handle_customer_name(
        self,
        context: ActionExecutionContext,
    ) -> ActionResult:
        name = _require_payload_value(context, "name", str).strip()
        if not name:
            raise InvalidActionInputError("Customer name must not be empty.")
        phone = context.booking_context.phone
        if phone is None:
            raise InvalidActionInputError("Customer phone is required before name.")
        context.booking_context.customer = Customer(phone=phone, name=name)
        return ActionResult("handle_customer_name", name)

    # Tạo booking thật trên POS sau final confirmation và idempotency key đã sẵn sàng.
    async def _create_booking(
        self,
        context: ActionExecutionContext,
    ) -> ActionResult:
        assert self._create_booking_handler is not None
        assert context.idempotency_key is not None
        result = await self._create_booking_handler.execute(
            context.booking_context,
            context.idempotency_key,
        )
        _ensure_success(result)
        _apply_context_updates(context.booking_context, result)
        return ActionResult("create_booking", result.data["create_result"])


# Chuyển HandlerResult không thành công thành lỗi để StateMachine đi failure path.
def _ensure_success(result: HandlerResult) -> None:
    if result.outcome is HandlerOutcome.SUCCESS:
        return
    raise InvalidBookingDataError(result.error_code or result.outcome.value)


# Lấy tuple item typed từ HandlerResult để action không dùng dữ liệu sai contract.
def _typed_result_items(
    result: HandlerResult,
    key: str,
    item_type: type[T],
) -> tuple[T, ...]:
    value = result.data.get(key)
    if not isinstance(value, tuple) or any(not isinstance(item, item_type) for item in value):
        raise InvalidBookingDataError(f"Handler result '{key}' is invalid.")
    return value


# Áp dụng context_updates từ handler sau khi đã xác thực field thuộc BookingContext.
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


def _should_preserve_recovery_selection(context: BookingContext) -> bool:
    return context.last_failure_code in {"no_slots_available", "no_working_shift"} and (
        context.main_course is not None or context.duration_minutes is not None
    )


def _apply_context_updates(
    context: BookingContext,
    result: HandlerResult,
) -> None:
    allowed_fields = {item.name for item in fields(BookingContext)}
    unknown = set(result.context_updates) - allowed_fields
    if unknown:
        raise InvalidBookingDataError("Handler returned unknown context updates.")
    for name, value in result.context_updates.items():
        setattr(context, name, value)
