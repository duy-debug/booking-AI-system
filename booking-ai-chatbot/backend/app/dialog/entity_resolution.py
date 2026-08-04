"""Resolve NLU entity queries through application search use cases."""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType

from app.application.handlers.search_service_handler import SearchServiceHandler
from app.application.handlers.search_shop_handler import SearchShopHandler
from app.dialog.dialog_controller import DialogTurnInput
from app.dialog.nlu import (
    NLUEntityKind,
    NLUResolutionStatus,
    NLUResult,
    StateIntentPolicy,
)
from app.domain.booking import (
    CourseSelection,
    CourseType,
    Service,
    Shop,
    TherapistPreference,
    TherapistPreferenceType,
)
from app.domain.booking_context import BookingContext, ServiceSelectionMode
from app.domain.booking_state import BookingState
from app.domain.exceptions import InvalidCourseSelectionError

_SAFE_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
_SELECTION_KEY_PATTERN = re.compile(r"^(?:shop|course):\d+$")
_SAFE_METADATA_KEYS = frozenset(
    {"address", "duration_minutes", "price", "course_type"}
)


class EntityResolutionStatus(StrEnum):
    """Describes the outcome of one authoritative entity lookup."""

    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    NOT_FOUND = "not_found"
    UNSUPPORTED = "unsupported"
    FAILED = "failed"


class EntityResolutionError(Exception):
    """Base exception for entity-resolution contract misuse."""


class InvalidEntityResolutionRequestError(EntityResolutionError):
    """Raised when a coordinator receives an invalid NLU resolution request."""


class InvalidCandidateSelectionError(EntityResolutionError):
    """Raised when an ambiguous candidate cannot be selected safely."""


class EntityResolutionNotDispatchableError(EntityResolutionError):
    """Raised when a resolution result cannot become a dialog turn."""


@dataclass(frozen=True, slots=True)
class EntityCandidate:
    """Contains UI-safe candidate data and an opaque local selection key."""

    kind: NLUEntityKind
    display_name: str
    selection_key: str
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.kind, NLUEntityKind):
            raise TypeError("Entity candidate kind is invalid.")
        if not isinstance(self.display_name, str) or not self.display_name.strip():
            raise ValueError("Entity candidate display name must not be empty.")
        if not _SELECTION_KEY_PATTERN.fullmatch(self.selection_key):
            raise ValueError("Entity candidate selection key is invalid.")
        object.__setattr__(self, "display_name", self.display_name.strip())
        object.__setattr__(self, "metadata", _safe_candidate_metadata(self.metadata))


@dataclass(frozen=True, slots=True)
class _CandidateDispatch:
    dispatch_intent: str
    dispatch_payload: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "dispatch_payload",
            MappingProxyType(dict(self.dispatch_payload)),
        )


@dataclass(frozen=True, slots=True)
class EntityResolutionResult:
    """Contains a safe entity-resolution outcome without raw adapter data."""

    status: EntityResolutionStatus
    entity_kind: NLUEntityKind
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

    def __post_init__(self) -> None:
        if not isinstance(self.status, EntityResolutionStatus):
            raise TypeError("Entity resolution status is invalid.")
        if not isinstance(self.entity_kind, NLUEntityKind):
            raise TypeError("Entity resolution kind is invalid.")
        if type(self.matched_count) is not int or self.matched_count < 0:
            raise ValueError("Matched count must be a non-negative integer.")
        if self.failure_code is not None and not _SAFE_CODE_PATTERN.fullmatch(
            self.failure_code
        ):
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
        if self.status in {
            EntityResolutionStatus.NOT_FOUND,
            EntityResolutionStatus.UNSUPPORTED,
            EntityResolutionStatus.FAILED,
        } and self.failure_code is None:
            raise ValueError("Unsuccessful entity result requires a safe failure code.")


class EntityResolutionCoordinator:
    """Coordinate safe shop, course and therapist entity resolution."""

    def __init__(
        self,
        *,
        search_shop_handler: SearchShopHandler,
        search_service_handler: SearchServiceHandler,
    ) -> None:
        self._search_shop_handler = search_shop_handler
        self._search_service_handler = search_service_handler

    async def resolve(
        self,
        *,
        nlu_result: NLUResult,
        state: BookingState,
        context: BookingContext,
    ) -> EntityResolutionResult:
        """Resolve one valid entity query without mutating dialog context."""
        kind, query, change_target = _validate_resolution_request(nlu_result, state)
        if kind is NLUEntityKind.SHOP:
            return await self._resolve_shop(query, change=change_target == "shop")
        if kind is NLUEntityKind.COURSE:
            return await self._resolve_course(
                query,
                context,
                change=change_target == "service",
            )
        return self._resolve_therapist(query)

    def select_candidate(
        self,
        *,
        result: EntityResolutionResult,
        selection_key: str,
    ) -> EntityResolutionResult:
        """Resolve an existing ambiguous candidate without another lookup."""
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

    async def _resolve_shop(
        self,
        query: str,
        *,
        change: bool = False,
    ) -> EntityResolutionResult:
        try:
            shops = await self._search_shop_handler.execute(query)
        except Exception:
            return _failure(
                NLUEntityKind.SHOP,
                "shop_resolution_unavailable",
            )
        if not shops:
            return _not_found(NLUEntityKind.SHOP, "shop_not_found")
        dispatches = tuple(
            _CandidateDispatch(
                "change_info" if change else "select_store",
                (
                    {"change_target": "shop", "shop": shop}
                    if change
                    else {"shop": shop}
                ),
            )
            for shop in shops
        )
        if len(shops) == 1:
            return _resolved_result(NLUEntityKind.SHOP, dispatches[0])
        candidates = tuple(
            EntityCandidate(
                kind=NLUEntityKind.SHOP,
                display_name=shop.name,
                selection_key=f"shop:{index}",
                metadata={"address": shop.address} if shop.address else {},
            )
            for index, shop in enumerate(shops)
        )
        return _ambiguous_result(NLUEntityKind.SHOP, candidates, dispatches)

    async def _resolve_course(
        self,
        query: str,
        context: BookingContext,
        *,
        change: bool = False,
    ) -> EntityResolutionResult:
        if context.shop is None:
            return _failure(
                NLUEntityKind.COURSE,
                "shop_required_before_course_resolution",
            )
        try:
            course_type = None
            if not change:
                course_type = (
                    CourseType.ADDON
                    if context.service_selection_mode is ServiceSelectionMode.ADDON
                    else CourseType.MAIN
                )
            services = await self._search_service_handler.execute(
                context.shop.shop_id,
                query,
                course_type=course_type,
            )
        except Exception:
            return _failure(
                NLUEntityKind.COURSE,
                "course_resolution_unavailable",
            )
        if course_type is CourseType.MAIN and context.duration_minutes is not None:
            services = [
                service
                for service in services
                if service.course_type is CourseType.MAIN
                and service.duration_minutes == context.duration_minutes
            ]
        if not services:
            return _not_found(NLUEntityKind.COURSE, "course_not_found")

        dispatches: list[_CandidateDispatch] = []
        for service in services:
            selection = _build_course_selection(
                service,
                context,
                replace_existing=change,
            )
            if selection is None:
                return _unsupported(NLUEntityKind.COURSE, "main_course_required")
            dispatches.append(
                _CandidateDispatch(
                    "change_info" if change else "select_course",
                    (
                        {
                            "change_target": "service",
                            "course_selection": selection,
                        }
                        if change
                        else {"course_selection": selection}
                    ),
                )
            )
        if len(services) == 1:
            return _resolved_result(NLUEntityKind.COURSE, dispatches[0])
        candidates = tuple(
            EntityCandidate(
                kind=NLUEntityKind.COURSE,
                display_name=service.name,
                selection_key=f"course:{index}",
                metadata={
                    "duration_minutes": service.duration_minutes,
                    "price": service.price,
                    "course_type": service.course_type.value,
                },
            )
            for index, service in enumerate(services)
        )
        return _ambiguous_result(
            NLUEntityKind.COURSE,
            candidates,
            tuple(dispatches),
        )

    @staticmethod
    def _resolve_therapist(query: str) -> EntityResolutionResult:
        preference_type = {
            "male": TherapistPreferenceType.MALE,
            "female": TherapistPreferenceType.FEMALE,
        }.get(query)
        if preference_type is None:
            return _unsupported(
                NLUEntityKind.THERAPIST,
                "therapist_lookup_not_supported",
            )
        preference = TherapistPreference(preference_type)
        return _resolved_result(
            NLUEntityKind.THERAPIST,
            _CandidateDispatch(
                "select_therapist",
                {"therapist_preference": preference},
            ),
        )


def entity_resolution_to_dialog_turn_input(
    result: EntityResolutionResult,
    *,
    state: BookingState,
    intent_policy: StateIntentPolicy,
    idempotency_key: str | None = None,
) -> DialogTurnInput:
    """Map only a resolved, policy-valid Domain payload to a dialog turn."""
    if (
        result.status is not EntityResolutionStatus.RESOLVED
        or result.dispatch_intent is None
    ):
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


def _validate_resolution_request(
    result: NLUResult,
    state: BookingState,
) -> tuple[NLUEntityKind, str, str | None]:
    if (
        result.resolution_status
        is not NLUResolutionStatus.ENTITY_RESOLUTION_REQUIRED
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
        NLUEntityKind.SHOP: BookingState.SELECTING_SHOP,
        NLUEntityKind.COURSE: BookingState.SELECTING_SERVICE,
        NLUEntityKind.THERAPIST: BookingState.SELECTING_THERAPIST,
    }[result.entity_kind]
    if result.change_target is None and state is not expected_state:
        raise InvalidEntityResolutionRequestError(
            "Entity kind is not valid for the current dialog state."
        )
    expected_change_kind = {
        "shop": NLUEntityKind.SHOP,
        "service": NLUEntityKind.COURSE,
    }
    if (
        result.change_target is not None
        and expected_change_kind.get(result.change_target) is not result.entity_kind
    ):
        raise InvalidEntityResolutionRequestError(
            "Change target does not match the requested entity kind."
        )
    return result.entity_kind, result.entity_query, result.change_target


def _build_course_selection(
    service: Service,
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
        if context.service is None:
            return None
        return CourseSelection(
            context.service,
            context.addons + (service,),
        )
    except InvalidCourseSelectionError:
        return None


def _resolved_result(
    kind: NLUEntityKind,
    dispatch: _CandidateDispatch,
) -> EntityResolutionResult:
    return EntityResolutionResult(
        status=EntityResolutionStatus.RESOLVED,
        entity_kind=kind,
        dispatch_intent=dispatch.dispatch_intent,
        dispatch_payload=dispatch.dispatch_payload,
        matched_count=1,
    )


def _not_found(kind: NLUEntityKind, code: str) -> EntityResolutionResult:
    return EntityResolutionResult(
        status=EntityResolutionStatus.NOT_FOUND,
        entity_kind=kind,
        dispatch_intent=None,
        dispatch_payload={},
        failure_code=code,
    )


def _unsupported(kind: NLUEntityKind, code: str) -> EntityResolutionResult:
    return EntityResolutionResult(
        status=EntityResolutionStatus.UNSUPPORTED,
        entity_kind=kind,
        dispatch_intent=None,
        dispatch_payload={},
        failure_code=code,
    )


def _failure(kind: NLUEntityKind, code: str) -> EntityResolutionResult:
    return EntityResolutionResult(
        status=EntityResolutionStatus.FAILED,
        entity_kind=kind,
        dispatch_intent=None,
        dispatch_payload={},
        failure_code=code,
    )


def _ambiguous_result(
    kind: NLUEntityKind,
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
        elif target == "service":
            expected_change = ("course_selection", CourseSelection)
        else:
            raise EntityResolutionNotDispatchableError(
                "Resolved change entity has an invalid target."
            )
        change_key, change_type = expected_change
        if frozenset(payload) != {"change_target", change_key} or not isinstance(
            payload[change_key], change_type
        ):
            raise EntityResolutionNotDispatchableError(
                "Resolved change entity payload is invalid."
            )
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
