"""Resolve NLU entity queries through application search use cases."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from app.application.handlers.search_course_handler import SearchCourseHandler
from app.application.handlers.search_shop_handler import SearchShopHandler
from app.domain.booking_context import BookingContext, CourseSelectionMode
from app.domain.booking_models import (
    AvailableTherapistRequest,
    Course,
    CourseSelection,
    CourseType,
    InvalidCourseSelectionError,
    Shop,
    TherapistAvailabilityGateway,
    TherapistPreference,
    TherapistPreferenceType,
)
from app.domain.booking_state import BookingState
from app.domain.outcomes import HandlerOutcome

if TYPE_CHECKING:
    from app.dialog.dialog_controller import DialogTurnInput

_SAFE_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
_SELECTION_KEY_PATTERN = re.compile(r"^(?:shop|course|therapist):\d+$")
_SAFE_METADATA_KEYS = frozenset({"address", "duration_minutes", "price", "course_type"})
_ENTITY_RESOLUTION_REQUIRED = "entity_resolution_required"
_ENTITY_KIND_SHOP = "shop"
_ENTITY_KIND_COURSE = "course"
_ENTITY_KIND_THERAPIST = "therapist"
_VALID_ENTITY_KINDS = frozenset({_ENTITY_KIND_SHOP, _ENTITY_KIND_COURSE, _ENTITY_KIND_THERAPIST})


def _kind_value(kind: object) -> str:
    value = getattr(kind, "value", kind)
    return value if isinstance(value, str) else ""


# Status resolver phân biệt rõ resolved/ambiguous/not_found để dialog chọn recovery đúng.
class EntityResolutionStatus(StrEnum):
    """Describes the outcome of one authoritative entity lookup."""

    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    NOT_FOUND = "not_found"
    UNSUPPORTED = "unsupported"
    FAILED = "failed"


# Nhóm lỗi resolver biểu diễn misuse contract, không phải lỗi user nhập sai.
class EntityResolutionError(Exception):
    """Base exception for entity-resolution contract misuse."""


class InvalidEntityResolutionRequestError(EntityResolutionError):
    """Raised when a coordinator receives an invalid NLU resolution request."""


class InvalidCandidateSelectionError(EntityResolutionError):
    """Raised when an ambiguous candidate cannot be selected safely."""


class EntityResolutionNotDispatchableError(EntityResolutionError):
    """Raised when a resolution result cannot become a dialog turn."""


# Candidate resolver dùng selection_key nội bộ để user chọn lại mà không expose raw model.
@dataclass(frozen=True, slots=True)
class EntityCandidate:
    """Contains UI-safe candidate data and an opaque local selection key."""

    kind: object
    display_name: str
    selection_key: str
    metadata: Mapping[str, object] = field(default_factory=dict)

    # Đóng băng dispatch candidate để lựa chọn lại không gọi POS lần nữa.
    def __post_init__(self) -> None:
        if _kind_value(self.kind) not in _VALID_ENTITY_KINDS:
            raise TypeError("Entity candidate kind is invalid.")
        if not isinstance(self.display_name, str) or not self.display_name.strip():
            raise ValueError("Entity candidate display name must not be empty.")
        if not _SELECTION_KEY_PATTERN.fullmatch(self.selection_key):
            raise ValueError("Entity candidate selection key is invalid.")
        object.__setattr__(self, "display_name", self.display_name.strip())
        object.__setattr__(self, "metadata", _safe_candidate_metadata(self.metadata))


# Dispatch payload được cache theo candidate để ambiguity selection không phải gọi POS lại.
@dataclass(frozen=True, slots=True)
class _CandidateDispatch:
    dispatch_intent: str
    dispatch_payload: Mapping[str, object]

    # Đóng băng payload dispatch để candidate cache không bị mutate giữa các turn.
    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "dispatch_payload",
            MappingProxyType(dict(self.dispatch_payload)),
        )


# Kết quả resolver là contract an toàn để controller quyết định dispatch hay hỏi lại user.
@dataclass(frozen=True, slots=True)
class EntityResolutionResult:
    """Contains a safe entity-resolution outcome without raw adapter data."""

    status: EntityResolutionStatus
    entity_kind: object
    dispatch_intent: str | None
    dispatch_payload: Mapping[str, object]
    candidates: tuple[EntityCandidate, ...] = ()
    failure_code: str | None = None
    matched_count: int = 0
    _candidate_dispatches: Mapping[str, _CandidateDispatch] = field(
        default_factory=dict,
        repr=False,
        compare=False,
    )

    # Validate shape theo status để không có result mơ hồ
    # vừa chứa failure vừa chứa dispatch payload.
    def __post_init__(self) -> None:
        if not isinstance(self.status, EntityResolutionStatus):
            raise TypeError("Entity resolution status is invalid.")
        if _kind_value(self.entity_kind) not in _VALID_ENTITY_KINDS:
            raise TypeError("Entity resolution kind is invalid.")
        if type(self.matched_count) is not int or self.matched_count < 0:
            raise ValueError("Matched count must be a non-negative integer.")
        if self.failure_code is not None and not _SAFE_CODE_PATTERN.fullmatch(self.failure_code):
            raise ValueError("Entity resolution failure code is invalid.")
        object.__setattr__(
            self,
            "dispatch_payload",
            MappingProxyType(dict(self.dispatch_payload)),
        )
        object.__setattr__(self, "candidates", tuple(self.candidates))
        object.__setattr__(
            self,
            "_candidate_dispatches",
            MappingProxyType(dict(self._candidate_dispatches)),
        )
        self._validate_status_shape()

    # Đảm bảo mỗi status resolution có đúng shape dữ liệu và failure code phù hợp.
    def _validate_status_shape(self) -> None:
        if self.status is EntityResolutionStatus.RESOLVED:
            if self.dispatch_intent is None or not self.dispatch_payload:
                raise ValueError("Resolved entity requires dispatch intent and payload.")
            if self.failure_code is not None:
                raise ValueError("Resolved entity cannot contain a failure code.")
            return
        if self.dispatch_intent is not None or self.dispatch_payload:
            raise ValueError("Non-resolved entity result cannot contain dispatch data.")
        if self.status is EntityResolutionStatus.AMBIGUOUS:
            if len(self.candidates) < 2 or self.matched_count != len(self.candidates):
                raise ValueError("Ambiguous entity result requires all matched candidates.")
            if self.failure_code is not None:
                raise ValueError("Ambiguous entity result cannot contain a failure code.")
        elif self.candidates:
            raise ValueError("Only ambiguous results may expose candidates.")
        if (
            self.status
            in {
                EntityResolutionStatus.NOT_FOUND,
                EntityResolutionStatus.UNSUPPORTED,
                EntityResolutionStatus.FAILED,
            }
            and self.failure_code is None
        ):
            raise ValueError("Unsuccessful entity result requires a safe failure code.")


# Coordinator resolve entity bằng handler nghiệp vụ, không tự match string ngoài nguồn POS.
class EntityResolutionCoordinator:
    """
    Resolve entity query từ NLU sang domain payload hoặc candidate ambiguity an toàn.

    Coordinator này chỉ chạy khi NLU chưa thể dispatch trực tiếp vì còn cần
    tra cứu authoritative như shop, course hoặc therapist.
    """

    # Nhận các search handler thật để resolve tên shop/course/therapist qua nguồn nghiệp vụ.
    def __init__(
        self,
        *,
        search_shop_handler: SearchShopHandler,
        search_course_handler: SearchCourseHandler,
        booking_gateway: TherapistAvailabilityGateway | None = None,
    ) -> None:
        self._search_shop_handler = search_shop_handler
        self._search_course_handler = search_course_handler
        self._booking_gateway = booking_gateway

    # Resolve entity query từ NLU thành domain payload hoặc candidate ambiguity an toàn.
    async def resolve(
        self,
        *,
        nlu_result: Any,
        state: BookingState,
        context: BookingContext,
    ) -> EntityResolutionResult:
        """Resolve một entity query hợp lệ mà không làm thay đổi `BookingContext`."""
        kind, query, change_target = _validate_resolution_request(nlu_result, state)
        kind_value = _kind_value(kind)
        if kind_value == _ENTITY_KIND_SHOP:
            return await self._resolve_shop(kind, query, change=change_target == "shop")
        if kind_value == _ENTITY_KIND_COURSE:
            return await self._resolve_course(
                kind,
                query,
                context,
                change_target=change_target,
            )
        return await self._resolve_therapist(kind, query, context)

    # Chọn candidate đã resolve trước đó mà không gọi lại handler/POS.
    def select_candidate(
        self,
        *,
        result: EntityResolutionResult,
        selection_key: str,
    ) -> EntityResolutionResult:
        """Chọn lại một candidate ambiguous đã có mà không phải gọi POS/handler lần nữa."""
        if result.status is not EntityResolutionStatus.AMBIGUOUS:
            raise InvalidCandidateSelectionError(
                "Candidate selection requires an ambiguous resolution result."
            )
        try:
            selected = result._candidate_dispatches[selection_key]
        except KeyError as error:
            raise InvalidCandidateSelectionError(
                "Candidate selection key does not exist in this result."
            ) from error
        return EntityResolutionResult(
            status=EntityResolutionStatus.RESOLVED,
            entity_kind=result.entity_kind,
            dispatch_intent=selected.dispatch_intent,
            dispatch_payload=selected.dispatch_payload,
            matched_count=1,
        )

    # Tìm shop qua handler và map 0/1/n kết quả thành not_found/resolved/ambiguous.
    async def _resolve_shop(
        self,
        kind: object,
        query: str,
        *,
        change: bool = False,
    ) -> EntityResolutionResult:
        try:
            result = await self._search_shop_handler.execute(query)
        except Exception:
            return _failure(
                kind,
                "shop_resolution_unavailable",
            )
        if result.outcome is HandlerOutcome.NOT_FOUND:
            return _not_found(kind, "shop_not_found")
        shops_value = result.data.get("shops")
        if result.outcome is not HandlerOutcome.SUCCESS or not isinstance(shops_value, tuple):
            return _failure(kind, "shop_resolution_unavailable")
        shops = shops_value
        dispatches = tuple(
            _CandidateDispatch(
                "change_info" if change else "select_store",
                ({"change_target": "shop", "shop": shop} if change else {"shop": shop}),
            )
            for shop in shops
        )
        if len(shops) == 1:
            return _resolved_result(kind, dispatches[0])
        candidates = tuple(
            EntityCandidate(
                kind=kind,
                display_name=shop.name,
                selection_key=f"shop:{index}",
                metadata={"address": shop.address} if shop.address else {},
            )
            for index, shop in enumerate(shops)
        )
        return _ambiguous_result(kind, candidates, dispatches)

    # Tìm liệu trình/add-on trong phạm vi shop hiện tại và tạo CourseSelection phù hợp.
    async def _resolve_course(
        self,
        kind: object,
        query: str,
        context: BookingContext,
        *,
        change_target: str | None = None,
    ) -> EntityResolutionResult:
        if context.shop is None:
            return _failure(
                kind,
                "shop_required_before_course_resolution",
            )
        try:
            course_type = None
            if change_target in {"main_course", "service"}:
                course_type = CourseType.MAIN
            elif change_target == "addon":
                course_type = CourseType.ADDON
            else:
                course_type = (
                    CourseType.ADDON
                    if context.course_selection_mode is CourseSelectionMode.ADDON
                    else CourseType.MAIN
                )
            result = await self._search_course_handler.execute(
                context.shop.shop_id,
                query,
                course_type=course_type,
            )
        except Exception:
            return _failure(
                kind,
                "course_resolution_unavailable",
            )
        if result.outcome is HandlerOutcome.NOT_FOUND:
            return _not_found(kind, "course_not_found")
        courses_value = result.data.get("courses")
        if result.outcome not in {
            HandlerOutcome.SUCCESS,
            HandlerOutcome.AMBIGUOUS,
        } or not isinstance(courses_value, tuple):
            return _failure(kind, "course_resolution_unavailable")
        courses = courses_value
        if course_type is CourseType.MAIN and context.duration_minutes is not None:
            courses = tuple(
                service
                for service in courses
                if service.course_type is CourseType.MAIN
                and service.duration_minutes == context.duration_minutes
            )
        if not courses:
            return _not_found(kind, "course_not_found")

        dispatches: list[_CandidateDispatch] = []
        for service in courses:
            selection = _build_course_selection(
                service,
                context,
                replace_existing=change_target in {"main_course", "service"},
            )
            if selection is None:
                return _unsupported(kind, "main_course_required")
            dispatches.append(
                _CandidateDispatch(
                    "change_info" if change_target is not None else "select_course",
                    (
                        {
                            "change_target": change_target,
                            "course_selection": selection,
                        }
                        if change_target is not None
                        else {"course_selection": selection}
                    ),
                )
            )
        if len(courses) == 1:
            return _resolved_result(kind, dispatches[0])
        candidates = tuple(
            EntityCandidate(
                kind=kind,
                display_name=service.name,
                selection_key=f"course:{index}",
                metadata={
                    "duration_minutes": service.duration_minutes,
                    "price": service.price,
                    "course_type": service.course_type.value,
                },
            )
            for index, service in enumerate(courses)
        )
        return _ambiguous_result(
            kind,
            candidates,
            tuple(dispatches),
        )

    # Resolve yêu cầu therapist theo giới tính hoặc tên, tôn trọng chính sách nhóm/single booking.
    async def _resolve_therapist(
        self,
        kind: object,
        query: str,
        context: BookingContext,
    ) -> EntityResolutionResult:
        preference_type = {
            "male": TherapistPreferenceType.MALE,
            "female": TherapistPreferenceType.FEMALE,
            "none": TherapistPreferenceType.NONE,
        }.get(query)
        if preference_type is not None:
            preference = TherapistPreference(preference_type)
            return _resolved_result(
                kind,
                _CandidateDispatch(
                    "select_therapist",
                    {"therapist_preference": preference},
                ),
            )
        if context.num_customer != 1:
            return _unsupported(kind, "personal_therapist_group_forbidden")
        if (
            self._booking_gateway is None
            or context.shop is None
            or context.booking_date is None
            or context.start_time is None
            or context.total_duration_minutes is None
        ):
            return _failure(kind, "therapist_resolution_unavailable")
        end_time = (
            datetime.combine(context.booking_date, context.start_time)
            + timedelta(minutes=context.total_duration_minutes)
        ).time()
        try:
            therapists = await self._booking_gateway.search_available_therapists(
                AvailableTherapistRequest(
                    shop_id=context.shop.shop_id,
                    booking_date=context.booking_date,
                    start_time=context.start_time,
                    end_time=end_time,
                )
            )
        except Exception:
            return _failure(kind, "therapist_resolution_unavailable")
        normalized_query = query.casefold().strip()
        matches = [
            therapist
            for therapist in therapists
            if therapist.therapist_name is not None
            and normalized_query in therapist.therapist_name.casefold()
        ]
        if not matches:
            return _not_found(kind, "therapist_not_found")
        dispatches = tuple(
            _CandidateDispatch("select_therapist", {"therapist_preference": item})
            for item in matches
        )
        if len(matches) == 1:
            return _resolved_result(kind, dispatches[0])
        candidates = tuple(
            EntityCandidate(
                kind=kind,
                display_name=item.therapist_name or "Kỹ thuật viên",
                selection_key=f"therapist:{index}",
            )
            for index, item in enumerate(matches)
        )
        return _ambiguous_result(kind, candidates, dispatches)


# Chuyển entity resolution đã resolved thành DialogTurnInput để chạy tiếp StateMachine.
def entity_resolution_to_dialog_turn_input(
    result: EntityResolutionResult,
    *,
    state: BookingState,
    intent_policy: Any,
    idempotency_key: str | None = None,
) -> "DialogTurnInput":
    """Map only a resolved, policy-valid Domain payload to a dialog turn."""
    from app.dialog.dialog_controller import DialogTurnInput

    if result.status is not EntityResolutionStatus.RESOLVED or result.dispatch_intent is None:
        raise EntityResolutionNotDispatchableError(
            "Entity resolution result is not resolved for dispatch."
        )
    if not intent_policy.is_allowed(state, result.dispatch_intent):
        raise EntityResolutionNotDispatchableError(
            "Resolved entity intent is not allowed in the current state."
        )
    _validate_resolution_payload(result.dispatch_intent, result.dispatch_payload)
    return DialogTurnInput(
        intent=result.dispatch_intent,
        payload=result.dispatch_payload,
        idempotency_key=idempotency_key,
    )


# Validate state/entity trước khi gọi resolver để không lookup sai loại hoặc sai state.
def _validate_resolution_request(
    result: Any,
    state: BookingState,
) -> tuple[object, str, str | None]:
    if (
        _kind_value(result.resolution_status) != _ENTITY_RESOLUTION_REQUIRED
        or result.intent is not None
        or result.payload
        or result.entity_kind is None
        or result.entity_query is None
        or not result.entity_query.strip()
    ):
        raise InvalidEntityResolutionRequestError(
            "NLU result does not satisfy the entity-resolution request contract."
        )
    expected_state = {
        _ENTITY_KIND_SHOP: BookingState.SELECTING_SHOP,
        _ENTITY_KIND_COURSE: BookingState.SELECTING_SERVICE,
        _ENTITY_KIND_THERAPIST: BookingState.SELECTING_THERAPIST,
    }[_kind_value(result.entity_kind)]
    if result.change_target is None and state is not expected_state:
        raise InvalidEntityResolutionRequestError(
            "Entity kind is not valid for the current dialog state."
        )
    expected_change_kind = {
        "shop": _ENTITY_KIND_SHOP,
        "main_course": _ENTITY_KIND_COURSE,
        "service": _ENTITY_KIND_COURSE,
        "addon": _ENTITY_KIND_COURSE,
    }
    if (
        result.change_target is not None
        and expected_change_kind.get(result.change_target) != _kind_value(result.entity_kind)
    ):
        raise InvalidEntityResolutionRequestError(
            "Change target does not match the requested entity kind."
        )
    return result.entity_kind, result.entity_query, result.change_target


# Ghép main course và add-on theo mode hiện tại của BookingContext.
def _build_course_selection(
    service: Course,
    context: BookingContext,
    *,
    replace_existing: bool = False,
) -> CourseSelection | None:
    try:
        if service.course_type is CourseType.MAIN:
            return CourseSelection(
                service,
                () if replace_existing else context.addons,
            )
        if replace_existing:
            return None
        if context.main_course is None:
            return None
        return CourseSelection(
            context.main_course,
            context.addons + (service,),
        )
    except InvalidCourseSelectionError:
        return None


# Tạo EntityResolutionResult thành công từ dispatch đã được validate.
def _resolved_result(
    kind: object,
    dispatch: _CandidateDispatch,
) -> EntityResolutionResult:
    return EntityResolutionResult(
        status=EntityResolutionStatus.RESOLVED,
        entity_kind=kind,
        dispatch_intent=dispatch.dispatch_intent,
        dispatch_payload=dispatch.dispatch_payload,
        matched_count=1,
    )


# Tạo kết quả không tìm thấy để renderer trả hướng dẫn nhập lại.
def _not_found(kind: object, code: str) -> EntityResolutionResult:
    return EntityResolutionResult(
        status=EntityResolutionStatus.NOT_FOUND,
        entity_kind=kind,
        dispatch_intent=None,
        dispatch_payload={},
        failure_code=code,
    )


# Tạo kết quả unsupported khi loại entity không thể resolve ở trạng thái hiện tại.
def _unsupported(kind: object, code: str) -> EntityResolutionResult:
    return EntityResolutionResult(
        status=EntityResolutionStatus.UNSUPPORTED,
        entity_kind=kind,
        dispatch_intent=None,
        dispatch_payload={},
        failure_code=code,
    )


# Tạo failure an toàn khi handler/POS lỗi hoặc response không đúng contract.
def _failure(kind: object, code: str) -> EntityResolutionResult:
    return EntityResolutionResult(
        status=EntityResolutionStatus.FAILED,
        entity_kind=kind,
        dispatch_intent=None,
        dispatch_payload={},
        failure_code=code,
    )


# Tạo danh sách candidate hiển thị khi có nhiều kết quả cùng phù hợp.
def _ambiguous_result(
    kind: object,
    candidates: tuple[EntityCandidate, ...],
    dispatches: tuple[_CandidateDispatch, ...],
) -> EntityResolutionResult:
    return EntityResolutionResult(
        status=EntityResolutionStatus.AMBIGUOUS,
        entity_kind=kind,
        dispatch_intent=None,
        dispatch_payload={},
        candidates=candidates,
        matched_count=len(candidates),
        _candidate_dispatches=MappingProxyType(
            {
                candidate.selection_key: dispatch
                for candidate, dispatch in zip(candidates, dispatches, strict=True)
            }
        ),
    )


# Lọc metadata candidate để không lộ UUID/raw payload ra response.
def _safe_candidate_metadata(values: Mapping[str, object]) -> Mapping[str, object]:
    safe: dict[str, object] = {}
    for key, value in values.items():
        if key not in _SAFE_METADATA_KEYS:
            continue
        if key in {"address", "course_type"} and isinstance(value, str):
            safe[key] = value
        elif key == "duration_minutes" and type(value) is int and value > 0:
            safe[key] = value
        elif key == "price" and isinstance(value, Decimal):
            safe[key] = value
    return MappingProxyType(safe)


# Kiểm tra payload domain sau resolution trước khi chuyển sang DialogTurnInput.
def _validate_resolution_payload(
    intent: str,
    payload: Mapping[str, object],
) -> None:
    expected: tuple[str, type[object]]
    if intent == "change_info":
        target = payload.get("change_target")
        expected_change: tuple[str, type[object]]
        if target == "shop":
            expected_change = ("shop", Shop)
        elif target in {"main_course", "service", "addon"}:
            expected_change = ("course_selection", CourseSelection)
        else:
            raise EntityResolutionNotDispatchableError(
                "Resolved change entity has an invalid target."
            )
        change_key, change_type = expected_change
        if frozenset(payload) != {"change_target", change_key} or not isinstance(
            payload[change_key], change_type
        ):
            raise EntityResolutionNotDispatchableError("Resolved change entity payload is invalid.")
        return
    if intent == "select_store":
        expected = ("shop", Shop)
    elif intent == "select_course":
        expected = ("course_selection", CourseSelection)
    elif intent == "select_therapist":
        expected = ("therapist_preference", TherapistPreference)
    else:
        raise EntityResolutionNotDispatchableError(
            "Resolved entity intent has no dispatch contract."
        )
    key, expected_type = expected
    if frozenset(payload) != {key} or not isinstance(payload[key], expected_type):
        raise EntityResolutionNotDispatchableError(
            "Resolved entity payload does not match its dispatch contract."
        )
