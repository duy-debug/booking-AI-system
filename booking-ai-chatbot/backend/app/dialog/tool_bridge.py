"""Registry and sequential executor for declarative dialog actions."""

import re
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, fields
from datetime import date, time
from typing import Protocol, TypeAlias, TypeVar

from app.application.exceptions import (
    CustomerVerificationMismatchError,
    InvalidIdempotencyKeyError,
    SlotConflictError,
)
from app.application.handlers.check_availability_handler import (
    CheckAvailabilityHandler,
)
from app.application.handlers.collect_customer_handler import CollectCustomerHandler
from app.application.handlers.confirm_phone_handler import ConfirmPhoneHandler
from app.application.handlers.create_booking_handler import CreateBookingHandler
from app.application.handlers.search_shop_handler import SearchShopHandler
from app.dialog.flow_loader import (
    FlowFailure,
    InvalidFlowConditionError,
)
from app.domain.booking import (
    CourseSelection,
    Shop,
    TherapistPreference,
    TherapistPreferenceType,
)
from app.domain.booking_context import BookingContext
from app.domain.booking_rules import BookingRules
from app.domain.booking_state import BookingState
from app.domain.exceptions import (
    BookingConflictError,
    BookingContextNotReadyError,
    CustomerNotAllowedError,
    CustomerVerificationRequiredError,
    InvalidBookingDataError,
    InvalidCourseSelectionError,
    InvalidDurationError,
    PhoneNotConfirmedError,
    TherapistNotAllowedForGroupError,
)

_ACTION_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
_EXTERNAL_SIDE_EFFECT_ACTIONS = frozenset({"create_booking", "retry_booking"})
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


class ToolBridgeError(Exception):
    """Base exception for action registry and execution failures."""


class DuplicateActionError(ToolBridgeError):
    """Raised when an action name is registered more than once."""


class UnknownActionError(ToolBridgeError):
    """Raised when an action name has no registered callable."""


class InvalidActionNameError(ToolBridgeError):
    """Raised when an action name does not follow the registry naming contract."""


class InvalidActionSequenceError(ToolBridgeError):
    """Raised when external side-effect actions are ordered unsafely."""


class InvalidActionInputError(ToolBridgeError):
    """Raised when an action is missing typed input required for execution."""


class ActionExecutionError(ToolBridgeError):
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


@dataclass(frozen=True, slots=True)
class FailureExecutionResult:
    """Contains prepared failure metadata without rendering or state commit."""

    failure_code: str
    target: BookingState
    instruction_template: str | None
    action_report: ActionExecutionReport
    original_error: ActionExecutionError


def _require_payload_value(
    context: ActionExecutionContext,
    key: str,
    expected_type: type[T],
) -> T:
    if key not in context.payload:
        raise InvalidActionInputError(
            f"Action '{context.intent}' requires payload key '{key}'."
        )

    value = context.payload[key]
    invalid_bool = expected_type is int and isinstance(value, bool)
    if value is None or not isinstance(value, expected_type) or invalid_bool:
        raise InvalidActionInputError(
            f"Action '{context.intent}' requires '{key}' to be "
            f"{expected_type.__name__}."
        )
    return value


class ToolBridge:
    """Registers explicit action bindings and executes them sequentially."""

    def __init__(
        self,
        *,
        search_shop_handler: SearchShopHandler | None = None,
        check_availability_handler: CheckAvailabilityHandler | None = None,
        collect_customer_handler: CollectCustomerHandler | None = None,
        confirm_phone_handler: ConfirmPhoneHandler | None = None,
        create_booking_handler: CreateBookingHandler | None = None,
        failure_code_provider: FailureCodeProvider | None = None,
    ) -> None:
        self._actions: dict[str, ActionCallable] = {}
        self._search_shop_handler = search_shop_handler
        self._check_availability_handler = check_availability_handler
        self._collect_customer_handler = collect_customer_handler
        self._confirm_phone_handler = confirm_phone_handler
        self._create_booking_handler = create_booking_handler
        self._failure_code_provider = failure_code_provider
        self._register_domain_actions()
        self._register_injected_handler_actions()

    def register_action(self, name: str, action: ActionCallable) -> None:
        """Register an explicitly supplied async action without overriding."""
        normalized_name = self._normalize_action_name(name)
        if not callable(action):
            raise TypeError("Action must be callable.")
        if normalized_name in self._actions:
            raise DuplicateActionError(
                f"Action '{normalized_name}' is already registered."
            )
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
            raise UnknownActionError(
                f"Action '{normalized_name}' is not registered."
            ) from error

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
            "service_duration_mismatch",
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

    async def execute_failure_actions(
        self,
        failure: FlowFailure,
        context: ActionExecutionContext,
    ) -> ActionExecutionReport:
        """Execute recovery actions without applying the failure target."""
        forbidden = tuple(
            action
            for action in failure.actions
            if action in _EXTERNAL_SIDE_EFFECT_ACTIONS
        )
        if forbidden:
            raise InvalidActionSequenceError(
                "Failure actions must not create or retry a booking."
            )
        return await self.execute_actions(failure.actions, context)

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
            return "service_duration_mismatch"
        if isinstance(error, InvalidCourseSelectionError):
            return "combo_not_bookable"
        if isinstance(error, TherapistNotAllowedForGroupError):
            return "therapist_unavailable"
        if isinstance(error, InvalidBookingDataError):
            if action_name in {"handle_phone_collection", "validate_phone"}:
                return "invalid_phone"
            return "booking_data_incomplete"
        if action_name == "load_time_slots":
            return "slot_api_error"
        if action_name in {
            "create_booking",
            "retry_booking",
            "handle_phone_collection",
        }:
            return "booking_api_error"
        return "action_execution_error"

    @staticmethod
    def _validate_action_sequence(action_names: tuple[str, ...]) -> None:
        side_effects = tuple(
            name for name in action_names if name in _EXTERNAL_SIDE_EFFECT_ACTIONS
        )
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
        try:
            result = await action(context)
            if not isinstance(result, ActionResult):
                raise TypeError(
                    f"Action '{action_name}' must return ActionResult, "
                    f"not {type(result).__name__}."
                )
            if result.action_name != action_name:
                raise TypeError(
                    f"Action '{action_name}' returned result for "
                    f"'{result.action_name}'."
                )
            return result
        except Exception as error:
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
            ("handle_service_selection", self._handle_service_selection),
            ("handle_time_selection", self._handle_time_selection),
            ("handle_therapist_selection", self._handle_therapist_selection),
            ("change_shop", self._change_shop),
            ("change_date", self._change_date),
            ("change_people", self._change_people),
            ("change_duration", self._change_duration),
            ("change_service", self._change_service),
            ("change_time", self._change_time),
            ("change_therapist", self._change_therapist),
            ("change_phone", self._change_phone),
            ("skip_therapist", self._skip_therapist),
            ("skip_therapist_for_group", self._skip_therapist_for_group),
            ("clear_date", self._clear_date),
            ("validate_phone", self._validate_phone),
        )
        for name, action in bindings:
            self.register_action(name, action)

    def _register_injected_handler_actions(self) -> None:
        if self._search_shop_handler is not None:
            self.register_action("search_shop", self._search_shop)
        if self._check_availability_handler is not None:
            self.register_action("load_time_slots", self._load_time_slots)
        if self._collect_customer_handler is not None:
            self.register_action(
                "handle_phone_collection",
                self._handle_phone_collection,
            )
        if self._confirm_phone_handler is not None:
            self.register_action("mark_phone_confirmed", self._mark_phone_confirmed)
        if self._create_booking_handler is not None:
            self.register_action("create_booking", self._create_booking)
            self.register_action("retry_booking", self._retry_booking)

    async def _search_shop(
        self,
        context: ActionExecutionContext,
    ) -> ActionResult:
        assert self._search_shop_handler is not None
        shops = await self._search_shop_handler.execute()
        return ActionResult("search_shop", shops)

    async def _handle_store_selection(
        self,
        context: ActionExecutionContext,
    ) -> ActionResult:
        shop = _require_payload_value(context, "shop", Shop)
        context.booking_context.set_shop(shop)
        return ActionResult("handle_store_selection", shop)

    async def _handle_date_selection(
        self,
        context: ActionExecutionContext,
    ) -> ActionResult:
        booking_date = _require_payload_value(context, "booking_date", date)
        context.booking_context.set_booking_date(booking_date)
        return ActionResult("handle_date_selection", booking_date)

    async def _handle_people_selection(
        self,
        context: ActionExecutionContext,
    ) -> ActionResult:
        num_customer = _require_payload_value(context, "num_customer", int)
        context.booking_context.set_num_customer(num_customer)
        return ActionResult("handle_people_selection", num_customer)

    async def _handle_duration_selection(
        self,
        context: ActionExecutionContext,
    ) -> ActionResult:
        duration = _require_payload_value(context, "duration_minutes", int)
        context.booking_context.set_duration(duration)
        return ActionResult("handle_duration_selection", duration)

    async def _handle_service_selection(
        self,
        context: ActionExecutionContext,
    ) -> ActionResult:
        selection = _require_payload_value(
            context,
            "course_selection",
            CourseSelection,
        )
        context.booking_context.set_course_selection(selection)
        return ActionResult("handle_service_selection", selection)

    async def _handle_time_selection(
        self,
        context: ActionExecutionContext,
    ) -> ActionResult:
        start_time = _require_payload_value(context, "start_time", time)
        context.booking_context.set_start_time(start_time)
        return ActionResult("handle_time_selection", start_time)

    async def _handle_therapist_selection(
        self,
        context: ActionExecutionContext,
    ) -> ActionResult:
        preference = _require_payload_value(
            context,
            "therapist_preference",
            TherapistPreference,
        )
        context.booking_context.set_therapist_preference(preference)
        return ActionResult("handle_therapist_selection", preference)

    async def _change_shop(self, context: ActionExecutionContext) -> ActionResult:
        shop = context.payload.get("shop")
        if shop is not None and not isinstance(shop, Shop):
            raise InvalidActionInputError("Changed shop must be a Shop.")
        context.booking_context.change_shop(shop)
        return ActionResult("change_shop", shop)

    async def _change_date(self, context: ActionExecutionContext) -> ActionResult:
        booking_date = context.payload.get("booking_date")
        if booking_date is not None and type(booking_date) is not date:
            raise InvalidActionInputError("Changed booking date must be a date.")
        context.booking_context.change_booking_date(booking_date)
        return ActionResult("change_date", booking_date)

    async def _change_people(self, context: ActionExecutionContext) -> ActionResult:
        value = context.payload.get("num_customer")
        if value is not None and type(value) is not int:
            raise InvalidActionInputError("Changed customer count must be an integer.")
        context.booking_context.change_num_customer(value)
        return ActionResult("change_people", value)

    async def _change_duration(self, context: ActionExecutionContext) -> ActionResult:
        value = context.payload.get("duration_minutes")
        if value is not None and type(value) is not int:
            raise InvalidActionInputError("Changed duration must be an integer.")
        context.booking_context.change_duration(value)
        return ActionResult("change_duration", value)

    async def _change_service(self, context: ActionExecutionContext) -> ActionResult:
        selection = context.payload.get("course_selection")
        if selection is not None and not isinstance(selection, CourseSelection):
            raise InvalidActionInputError(
                "Changed service must be a CourseSelection."
            )
        context.booking_context.change_course_selection(selection)
        return ActionResult("change_service", selection)

    async def _change_time(self, context: ActionExecutionContext) -> ActionResult:
        start_time = context.payload.get("start_time")
        if start_time is not None and type(start_time) is not time:
            raise InvalidActionInputError("Changed start time must be a time.")
        context.booking_context.change_start_time(start_time)
        return ActionResult("change_time", start_time)

    async def _change_therapist(
        self,
        context: ActionExecutionContext,
    ) -> ActionResult:
        gender = context.payload.get("therapist_gender")
        if gender is not None and gender not in {"male", "female", "none"}:
            raise InvalidActionInputError("Changed therapist gender is invalid.")
        preference = (
            None
            if gender is None
            else TherapistPreference(TherapistPreferenceType(gender))
        )
        context.booking_context.change_therapist_preference(preference)
        return ActionResult("change_therapist", preference)

    async def _change_phone(self, context: ActionExecutionContext) -> ActionResult:
        phone = context.payload.get("phone")
        if phone is not None:
            if not isinstance(phone, str):
                raise InvalidActionInputError("Changed phone must be a string.")
            BookingRules.validate_phone(phone)
        context.booking_context.change_phone(phone)
        return ActionResult("change_phone", phone)

    async def _skip_therapist(
        self,
        context: ActionExecutionContext,
    ) -> ActionResult:
        preference = TherapistPreference(TherapistPreferenceType.NONE)
        context.booking_context.set_therapist_preference(preference)
        return ActionResult("skip_therapist", preference)

    async def _skip_therapist_for_group(
        self,
        context: ActionExecutionContext,
    ) -> ActionResult:
        if context.booking_context.num_customer not in (2, 3):
            raise InvalidActionInputError(
                "Action 'skip_therapist_for_group' requires two or three customers."
            )
        context.booking_context.set_therapist_preference(None)
        return ActionResult("skip_therapist_for_group")

    async def _clear_date(
        self,
        context: ActionExecutionContext,
    ) -> ActionResult:
        context.booking_context.set_booking_date(None)
        return ActionResult("clear_date")

    async def _validate_phone(
        self,
        context: ActionExecutionContext,
    ) -> ActionResult:
        phone = context.booking_context.phone
        if phone is None:
            raise InvalidActionInputError(
                "Action 'validate_phone' requires a collected phone."
            )
        BookingRules.validate_phone(phone)
        return ActionResult("validate_phone", phone)

    async def _load_time_slots(
        self,
        context: ActionExecutionContext,
    ) -> ActionResult:
        assert self._check_availability_handler is not None
        await self._check_availability_handler.execute(context.booking_context)
        return ActionResult(
            "load_time_slots",
            context.booking_context.available_slots,
        )

    async def _handle_phone_collection(
        self,
        context: ActionExecutionContext,
    ) -> ActionResult:
        assert self._collect_customer_handler is not None
        phone = _require_payload_value(context, "phone", str)
        name_value = context.payload.get("name")
        if name_value is not None and not isinstance(name_value, str):
            raise InvalidActionInputError(
                "Action 'handle_phone_collection' requires 'name' to be str."
            )
        result = await self._collect_customer_handler.execute(
            context.booking_context,
            phone,
            name_value,
        )
        return ActionResult("handle_phone_collection", result)

    async def _mark_phone_confirmed(
        self,
        context: ActionExecutionContext,
    ) -> ActionResult:
        assert self._confirm_phone_handler is not None
        self._confirm_phone_handler.execute(context.booking_context)
        return ActionResult("mark_phone_confirmed")

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
        return ActionResult("create_booking", result)

    async def _retry_booking(
        self,
        context: ActionExecutionContext,
    ) -> ActionResult:
        assert self._create_booking_handler is not None
        assert context.idempotency_key is not None
        result = await self._create_booking_handler.execute(
            context.booking_context,
            context.idempotency_key,
        )
        return ActionResult("retry_booking", result)
