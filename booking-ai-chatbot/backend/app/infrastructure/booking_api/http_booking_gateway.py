"""HTTP adapter for the verified subset of the POS booking contract."""

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, time
from decimal import Decimal, InvalidOperation
from time import perf_counter
from typing import cast
from uuid import UUID

import httpx

from app.application.exceptions import SlotConflictError
from app.application.ports.booking_gateway import (
    AvailabilityRequest,
    ChildReservationReference,
    CourseSearchRequest,
    CreateBookingRequest,
    CreateBookingResult,
    CustomerVerificationRequest,
    CustomerVerificationResult,
    FinalAvailabilityRequest,
    FinalAvailabilityResult,
)
from app.core.logging import elapsed_ms, trace_log
from app.domain.booking import (
    Booking,
    CourseType,
    Customer,
    Service,
    Shop,
    TherapistPreference,
)
from app.domain.exceptions import CustomerNotAllowedError
from app.infrastructure.booking_api.exceptions import (
    POSAuthenticationError,
    POSAuthorizationError,
    POSConflictError,
    POSConnectionError,
    POSContractNotConfiguredError,
    POSHTTPError,
    POSNotFoundError,
    POSRequestMappingError,
    POSResponseMappingError,
    POSTemporaryError,
    POSTimeoutError,
    POSUnexpectedStatusError,
    POSValidationError,
)


@dataclass(frozen=True, slots=True)
class _ParsedSlot:
    start_time: time
    available: bool
    reason_code: str | None
    message: str | None


@dataclass(frozen=True, slots=True)
class _ParsedReservation:
    reference: ChildReservationReference
    courses: tuple[Service, ...]


class HTTPBookingGateway:
    """Implement verified BookingGateway operations over an injected HTTP client."""

    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        base_url: str,
        timeout_seconds: float | None = None,
    ) -> None:
        normalized_base_url = base_url.strip().rstrip("/")
        if not normalized_base_url:
            raise ValueError("POS base URL must not be empty.")
        if timeout_seconds is not None and timeout_seconds <= 0:
            raise ValueError("POS timeout must be positive when provided.")

        self._client = client
        self._base_url = normalized_base_url
        self._timeout_seconds = timeout_seconds

    async def search_shops(self, query: str | None = None) -> list[Shop]:
        """Return the default active POS shop list when no keyword is requested."""
        if query is not None:
            raise POSContractNotConfiguredError(
                "POS shop search has no verified keyword parameter."
            )

        payload = await self._request_json(
            operation="search_shops",
            method="GET",
            path="/api/shops",
        )
        root = _mapping(payload, "shop response")
        items = _list(root, "data")
        _validate_shop_meta(root)
        return [_parse_shop(item, index) for index, item in enumerate(items)]

    async def search_services(
        self,
        request: CourseSearchRequest,
    ) -> list[Service]:
        """Return courses using only filters supported by the POS endpoint."""
        params = {"is_active": str(request.is_active).lower()}
        if request.course_type is not None:
            params["course_type"] = request.course_type.value
        payload = await self._request_json(
            operation="search_services",
            method="GET",
            path=f"/api/shops/{request.shop_id}/courses",
            params=params,
            expected_status=200,
        )
        root = _mapping(payload, "course response")
        return [
            _parse_service(item, index, expected_shop_id=request.shop_id)
            for index, item in enumerate(_list(root, "data"))
        ]

    async def get_available_slots(
        self,
        request: AvailabilityRequest,
    ) -> tuple[time, ...]:
        """Return available start times while preserving their POS order."""
        params = _availability_params(request)
        payload = await self._request_json(
            operation="get_available_slots",
            method="GET",
            path=f"/api/shops/{request.shop_id}/available-slots",
            params=params,
        )
        slots = _parse_slots(
            payload,
            shop_id=request.shop_id,
            booking_date=request.booking_date,
            num_customer=request.num_customer,
            duration_minutes=request.duration_minutes,
        )
        return tuple(slot.start_time for slot in slots if slot.available)

    async def verify_customer(
        self,
        request: CustomerVerificationRequest,
    ) -> CustomerVerificationResult:
        """Verify membership and NG eligibility for a phone at one shop."""
        payload = await self._request_json(
            operation="verify_customer",
            method="POST",
            path="/api/booking-eligibility-checks",
            json_body={"shop_id": str(request.shop_id), "phone": request.phone},
            expected_status=201,
        )
        return _parse_customer_verification(payload)

    async def check_final_availability(
        self,
        request: FinalAvailabilityRequest,
    ) -> FinalAvailabilityResult:
        """Recheck one selected slot through the POS start_time query contract."""
        params = _availability_params(request)
        params["start_time"] = request.start_time.isoformat(timespec="minutes")
        payload = await self._request_json(
            operation="check_final_availability",
            method="GET",
            path=f"/api/shops/{request.shop_id}/available-slots",
            params=params,
        )
        slots = _parse_slots(
            payload,
            shop_id=request.shop_id,
            booking_date=request.booking_date,
            num_customer=request.num_customer,
            duration_minutes=request.duration_minutes,
        )
        if not slots:
            return FinalAvailabilityResult(available=False)
        if len(slots) != 1 or slots[0].start_time != request.start_time:
            raise POSResponseMappingError(
                "POS final availability response did not contain exactly the requested slot."
            )

        slot = slots[0]
        return FinalAvailabilityResult(
            available=slot.available,
            reason=slot.reason_code or slot.message,
        )

    async def create_booking(
        self,
        request: CreateBookingRequest,
    ) -> CreateBookingResult:
        """Create one booking without retry and preserve child reservation IDs."""
        body = _create_booking_body(request)
        payload = await self._request_json(
            operation="create_booking",
            method="POST",
            path="/api/bookings",
            headers={"Idempotency-Key": request.idempotency_key},
            json_body=body,
            expected_status=201,
        )
        return _parse_create_booking_result(payload, request)

    async def lookup_booking(self, booking_id: UUID) -> Booking:
        """Fail because the public response cannot populate the domain customer phone."""
        raise POSContractNotConfiguredError(
            "POS booking detail omits customer phone required by the domain Booking model."
        )

    async def reschedule_booking(
        self,
        booking_id: UUID,
        booking_date: date,
        start_time: time,
    ) -> Booking:
        """Fail because the update response cannot populate the complete domain booking."""
        raise POSContractNotConfiguredError(
            "POS update response omits customer phone required by the domain Booking model."
        )

    async def cancel_booking(self, booking_id: UUID) -> Booking:
        """Fail because the cancel response cannot populate the complete domain booking."""
        raise POSContractNotConfiguredError(
            "POS cancel response omits customer phone required by the domain Booking model."
        )

    async def _request_json(
        self,
        *,
        operation: str,
        method: str,
        path: str,
        params: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        json_body: Mapping[str, object] | None = None,
        expected_status: int = 200,
    ) -> object:
        url = f"{self._base_url}{path}"
        started_at = perf_counter()
        try:
            if self._timeout_seconds is None:
                response = await self._client.request(
                    method,
                    url,
                    params=params,
                    headers=headers,
                    json=json_body,
                )
            else:
                response = await self._client.request(
                    method,
                    url,
                    params=params,
                    headers=headers,
                    json=json_body,
                    timeout=self._timeout_seconds,
                )
        except httpx.TimeoutException as exc:
            trace_log(
                logging.getLogger(__name__),
                logging.WARNING,
                "POS",
                "failed",
                operation=operation,
                method=method,
                endpoint=operation,
                error_code="pos_timeout",
                duration_ms=elapsed_ms(started_at),
            )
            raise POSTimeoutError(f"POS operation {operation!r} timed out.") from exc
        except httpx.RequestError as exc:
            trace_log(
                logging.getLogger(__name__),
                logging.WARNING,
                "POS",
                "failed",
                operation=operation,
                method=method,
                endpoint=operation,
                error_code="pos_connection_error",
                duration_ms=elapsed_ms(started_at),
            )
            raise POSConnectionError(
                f"POS operation {operation!r} could not reach the server."
            ) from exc

        if response.status_code != expected_status:
            trace_log(
                logging.getLogger(__name__),
                logging.WARNING,
                "POS",
                "failed",
                operation=operation,
                method=method,
                endpoint=operation,
                status_code=response.status_code,
                error_code=f"pos_http_{response.status_code}",
                duration_ms=elapsed_ms(started_at),
            )
            _raise_http_error(operation, response)
        try:
            payload = cast(object, response.json())
        except ValueError as exc:
            trace_log(
                logging.getLogger(__name__),
                logging.WARNING,
                "POS",
                "failed",
                operation=operation,
                method=method,
                endpoint=operation,
                status_code=response.status_code,
                error_code="pos_invalid_json",
                duration_ms=elapsed_ms(started_at),
            )
            raise POSResponseMappingError(
                f"POS operation {operation!r} returned invalid JSON."
            ) from exc
        trace_log(
            logging.getLogger(__name__),
            logging.INFO,
            "POS",
            "completed",
            operation=operation,
            method=method,
            endpoint=operation,
            status_code=response.status_code,
            item_count=_safe_item_count(payload),
            duration_ms=elapsed_ms(started_at),
        )
        return payload


def _safe_item_count(payload: object) -> int:
    if isinstance(payload, Mapping):
        data = payload.get("data")
        if isinstance(data, list):
            return len(data)
    return 0


def _availability_params(
    request: AvailabilityRequest | FinalAvailabilityRequest,
) -> dict[str, str]:
    params = {
        "booking_date": request.booking_date.isoformat(),
        "number_of_people": str(request.num_customer),
        "main_course_id": str(request.main_course_id),
        "therapist_request_type": "none",
    }
    if request.addon_ids:
        params["addon_course_ids"] = ",".join(str(item) for item in request.addon_ids)

    preference = request.therapist_preference
    if preference is not None:
        _apply_therapist_preference(params, preference)
    return params


def _create_booking_body(request: CreateBookingRequest) -> dict[str, object]:
    if not request.idempotency_key:
        raise POSRequestMappingError("POS create requires a non-empty idempotency key.")

    customer: dict[str, object] = {"phone": request.phone}
    if request.customer_name is not None:
        customer["name"] = request.customer_name
    body: dict[str, object] = {
        "shop_id": str(request.shop_id),
        "booking_date": request.booking_date.isoformat(),
        "start_time": request.start_time.isoformat(timespec="minutes"),
        "number_of_people": request.num_customer,
        "customer": customer,
        "courses": [
            {"course_id": str(request.main_course_id), "course_role": "main"},
            *(
                {"course_id": str(addon_id), "course_role": "addon"}
                for addon_id in request.addon_ids
            ),
        ],
        "confirmed_by_customer": True,
    }
    if request.therapist_preference is not None:
        body["therapist_request"] = _therapist_request_body(request.therapist_preference)
    return body


def _therapist_request_body(
    preference: TherapistPreference,
) -> dict[str, object]:
    preference_type = preference.preference_type.value
    if preference_type == "none":
        return {"type": "none"}
    if preference_type in {"male", "female"}:
        return {"type": "gender", "gender": preference_type}
    if preference_type == "personal" and preference.therapist_id is not None:
        try:
            UUID(preference.therapist_id)
        except ValueError as exc:
            raise POSRequestMappingError(
                "POS create requires a UUID for a personal therapist."
            ) from exc
        return {
            "type": "specific",
            "therapist_id": preference.therapist_id,
        }
    raise POSContractNotConfiguredError(
        "POS cannot create a personal therapist request by name alone."
    )


def _parse_customer_verification(payload: object) -> CustomerVerificationResult:
    root = _mapping(payload, "eligibility response")
    data = _mapping(_required(root, "data"), "eligibility data")
    _uuid(data, "check_id")
    phone = _string(data, "phone")
    if not _boolean(data, "eligible"):
        raise POSResponseMappingError(
            "POS returned an ineligible 201 response instead of its documented error."
        )
    if _required(data, "restriction") is not None:
        raise POSResponseMappingError("POS eligible response unexpectedly contains a restriction.")

    raw_customer = _required(data, "customer")
    if raw_customer is None:
        return CustomerVerificationResult(
            phone=phone,
            customer_id=None,
            member_rank=None,
            visit_count=None,
            ng_list_checked=True,
            is_ng_customer=False,
        )

    customer = _mapping(raw_customer, "eligibility customer")
    if _string(customer, "customer_type") != "existing":
        raise POSResponseMappingError("POS eligibility customer has an unknown customer_type.")
    customer_id = str(_uuid(customer, "customer_id"))
    _optional_string(customer, "name")
    _boolean(customer, "is_member")
    member_rank = _optional_string(customer, "member_rank")
    visit_count = _integer(customer, "visit_count")
    return CustomerVerificationResult(
        phone=phone,
        customer_id=customer_id,
        member_rank=member_rank,
        visit_count=visit_count,
        ng_list_checked=True,
        is_ng_customer=False,
    )


def _parse_create_booking_result(
    payload: object,
    request: CreateBookingRequest,
) -> CreateBookingResult:
    root = _mapping(payload, "create booking response")
    data = _mapping(_required(root, "data"), "create booking data")
    booking_id = _uuid(data, "booking_id")
    shop_id = _uuid(data, "shop_id")
    if shop_id != request.shop_id:
        raise POSResponseMappingError("POS create response contains a different shop_id.")
    shop_name = _string(data, "shop_name")
    _uuid(data, "customer_id")
    booking_date = _date(data, "booking_date")
    start_time = _time(data, "start_time")
    _time(data, "end_time")
    num_customer = _integer(data, "number_of_people")
    duration_minutes = _integer(data, "total_duration_minutes")
    status = _string(data, "status")
    _validate_create_response_correlation(
        data,
        request=request,
        booking_date=booking_date,
        start_time=start_time,
        num_customer=num_customer,
        duration_minutes=duration_minutes,
    )
    _optional_string(data, "cancel_reason")
    _optional_string(data, "cancelled_at")
    _string(data, "created_at")
    _string(data, "updated_at")

    reservations = tuple(
        _parse_reservation(item, index) for index, item in enumerate(_list(data, "reservations"))
    )
    if len(reservations) != num_customer:
        raise POSResponseMappingError("POS child reservation count differs from number_of_people.")
    first_courses = reservations[0].courses
    if any(item.courses != first_courses for item in reservations[1:]):
        raise POSResponseMappingError("POS group reservations contain different course snapshots.")
    main_courses = tuple(
        service for service in first_courses if service.course_type is CourseType.MAIN
    )
    addons = tuple(service for service in first_courses if service.course_type is CourseType.ADDON)
    if len(main_courses) != 1:
        raise POSResponseMappingError("POS booking response must contain exactly one main course.")
    if sum(service.duration_minutes for service in first_courses) != duration_minutes:
        raise POSResponseMappingError("POS course snapshots disagree with total_duration_minutes.")

    booking = Booking(
        booking_id=booking_id,
        status=status,
        shop=Shop(shop_id=shop_id, name=shop_name),
        service=main_courses[0],
        customer=Customer(phone=request.phone, name=request.customer_name),
        booking_date=booking_date,
        start_time=start_time,
        num_customer=num_customer,
        duration_minutes=duration_minutes,
        therapist_preference=request.therapist_preference,
        addons=addons,
    )
    return CreateBookingResult(
        booking=booking,
        child_reservations=tuple(item.reference for item in reservations),
    )


def _validate_create_response_correlation(
    data: Mapping[str, object],
    *,
    request: CreateBookingRequest,
    booking_date: date,
    start_time: time,
    num_customer: int,
    duration_minutes: int,
) -> None:
    if booking_date != request.booking_date or start_time != request.start_time:
        raise POSResponseMappingError(
            "POS create response date/time differs from the submitted request."
        )
    if num_customer != request.num_customer:
        raise POSResponseMappingError(
            "POS create response number_of_people differs from the request."
        )
    if duration_minutes != request.duration_minutes:
        raise POSResponseMappingError(
            "POS-derived duration differs from the application booking duration."
        )

    response_type = _string(data, "therapist_request_type")
    response_therapist = _optional_uuid(data, "requested_therapist_id")
    response_gender = _optional_string(data, "requested_gender")
    preference = request.therapist_preference
    if preference is None or preference.preference_type.value == "none":
        expected_type, expected_therapist, expected_gender = "none", None, None
    elif preference.preference_type.value in {"male", "female"}:
        expected_type = "gender"
        expected_therapist = None
        expected_gender = preference.preference_type.value
    else:
        expected_type = "specific"
        expected_therapist = UUID(preference.therapist_id or "")
        expected_gender = None
    if (
        response_type != expected_type
        or response_therapist != expected_therapist
        or response_gender != expected_gender
    ):
        raise POSResponseMappingError(
            "POS create response therapist request differs from the submitted request."
        )


def _parse_reservation(value: object, index: int) -> _ParsedReservation:
    reservation = _mapping(value, f"reservation[{index}]")
    reference = ChildReservationReference(
        reservation_id=_uuid(reservation, "reservation_id"),
        participant_index=_integer(reservation, "person_index"),
    )
    _uuid(reservation, "therapist_id")
    _string(reservation, "therapist_name")
    _time(reservation, "start_time")
    _time(reservation, "end_time")
    _string(reservation, "status")
    _string(reservation, "assignment_source")
    courses = tuple(
        _parse_reservation_course(item, course_index)
        for course_index, item in enumerate(_list(reservation, "courses"))
    )
    return _ParsedReservation(reference=reference, courses=courses)


def _parse_reservation_course(value: object, index: int) -> Service:
    course = _mapping(value, f"reservation course[{index}]")
    return Service(
        service_id=_uuid(course, "course_id"),
        name=_string(course, "course_name_snapshot"),
        duration_minutes=_integer(course, "duration_snapshot"),
        price=_decimal(course, "price_snapshot"),
        course_type=_course_type(course, "course_role"),
    )


def _apply_therapist_preference(
    params: dict[str, str],
    preference: TherapistPreference,
) -> None:
    preference_type = preference.preference_type.value
    if preference_type == "none":
        return
    if preference_type in {"male", "female"}:
        params["therapist_request_type"] = "gender"
        params["therapist_gender"] = preference_type
        return
    if preference_type == "personal" and preference.therapist_id is not None:
        try:
            UUID(preference.therapist_id)
        except ValueError as exc:
            raise POSRequestMappingError(
                "A POS-specific therapist preference requires a UUID therapist_id."
            ) from exc
        params["therapist_request_type"] = "specific"
        params["therapist_id"] = preference.therapist_id
        return
    raise POSContractNotConfiguredError(
        "POS cannot resolve a personal therapist preference by name alone."
    )


def _parse_slots(
    payload: object,
    *,
    shop_id: UUID,
    booking_date: date,
    num_customer: int,
    duration_minutes: int,
) -> list[_ParsedSlot]:
    root = _mapping(payload, "availability response")
    meta = _mapping(_required(root, "meta"), "availability meta")
    if _uuid(meta, "shop_id") != shop_id:
        raise POSResponseMappingError("POS availability meta contains a different shop_id.")
    if _date(meta, "booking_date") != booking_date:
        raise POSResponseMappingError("POS availability meta contains a different booking_date.")
    if _integer(meta, "number_of_people") != num_customer:
        raise POSResponseMappingError(
            "POS availability meta contains a different number_of_people."
        )

    parsed: list[_ParsedSlot] = []
    for index, item in enumerate(_list(root, "data")):
        slot = _mapping(item, f"availability data[{index}]")
        start = _time(slot, "start_time")
        _time(slot, "end_time")
        if _integer(slot, "duration_minutes") != duration_minutes:
            raise POSResponseMappingError(
                f"POS availability data[{index}] duration disagrees with the request."
            )
        available = _boolean(slot, "available")
        _integer(slot, "available_therapist_count")
        _integer(slot, "required_therapist_count")
        parsed.append(
            _ParsedSlot(
                start_time=start,
                available=available,
                reason_code=_optional_string(slot, "reason_code"),
                message=_optional_string(slot, "message"),
            )
        )
    return parsed


def _parse_shop(value: object, index: int) -> Shop:
    item = _mapping(value, f"shop data[{index}]")
    return Shop(
        shop_id=_uuid(item, "shop_id"),
        name=_string(item, "name"),
        address=_optional_string(item, "address"),
        phone=_optional_string(item, "phone"),
    )


def _parse_service(
    value: object,
    index: int,
    *,
    expected_shop_id: UUID,
) -> Service:
    item = _mapping(value, f"course data[{index}]")
    if _uuid(item, "shop_id") != expected_shop_id:
        raise POSResponseMappingError(f"POS course data[{index}] contains a different shop_id.")
    return Service(
        service_id=_uuid(item, "course_id"),
        name=_string(item, "name"),
        duration_minutes=_integer(item, "duration_minutes"),
        price=_decimal(item, "price"),
        course_type=_course_type(item, "course_type"),
    )


def _validate_shop_meta(root: Mapping[str, object]) -> None:
    meta = _mapping(_required(root, "meta"), "shop meta")
    total = _required(meta, "total")
    if isinstance(total, bool) or not isinstance(total, int):
        raise POSResponseMappingError("POS shop meta.total must be an integer.")


def _raise_http_error(operation: str, response: httpx.Response) -> None:
    code = _error_code(response)
    if code == "CUSTOMER_IN_NG_LIST":
        raise CustomerNotAllowedError("POS rejected a customer on its NG list.")
    if operation == "create_booking" and code == "SLOT_CONFLICT":
        raise SlotConflictError(nearest_slots=(), reason=code)
    error_type: type[POSHTTPError]
    if response.status_code == 401:
        error_type = POSAuthenticationError
    elif response.status_code == 403:
        error_type = POSAuthorizationError
    elif response.status_code == 404:
        error_type = POSNotFoundError
    elif response.status_code in {400, 422}:
        error_type = POSValidationError
    elif response.status_code == 409:
        error_type = POSConflictError
    elif response.status_code == 429 or 500 <= response.status_code < 600:
        error_type = POSTemporaryError
    else:
        error_type = POSUnexpectedStatusError
    raise error_type(
        operation=operation,
        status_code=response.status_code,
        code=code,
    )


def _error_code(response: httpx.Response) -> str | None:
    try:
        payload = response.json()
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    code = payload.get("code")
    return code if isinstance(code, str) else None


def _mapping(value: object, location: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise POSResponseMappingError(f"POS {location} must be an object.")
    return cast(dict[str, object], value)


def _required(value: Mapping[str, object], field: str) -> object:
    if field not in value:
        raise POSResponseMappingError(f"POS response is missing required field {field!r}.")
    return value[field]


def _list(value: Mapping[str, object], field: str) -> list[object]:
    result = _required(value, field)
    if not isinstance(result, list):
        raise POSResponseMappingError(f"POS field {field!r} must be a list.")
    return cast(list[object], result)


def _string(value: Mapping[str, object], field: str) -> str:
    result = _required(value, field)
    if not isinstance(result, str):
        raise POSResponseMappingError(f"POS field {field!r} must be a string.")
    return result


def _optional_string(value: Mapping[str, object], field: str) -> str | None:
    result = _required(value, field)
    if result is not None and not isinstance(result, str):
        raise POSResponseMappingError(f"POS field {field!r} must be a string or null.")
    return result


def _integer(value: Mapping[str, object], field: str) -> int:
    result = _required(value, field)
    if isinstance(result, bool) or not isinstance(result, int):
        raise POSResponseMappingError(f"POS field {field!r} must be an integer.")
    return result


def _boolean(value: Mapping[str, object], field: str) -> bool:
    result = _required(value, field)
    if not isinstance(result, bool):
        raise POSResponseMappingError(f"POS field {field!r} must be a boolean.")
    return result


def _uuid(value: Mapping[str, object], field: str) -> UUID:
    raw = _string(value, field)
    try:
        return UUID(raw)
    except ValueError as exc:
        raise POSResponseMappingError(f"POS field {field!r} must be a UUID.") from exc


def _optional_uuid(value: Mapping[str, object], field: str) -> UUID | None:
    raw = _required(value, field)
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise POSResponseMappingError(f"POS field {field!r} must be a UUID or null.")
    try:
        return UUID(raw)
    except ValueError as exc:
        raise POSResponseMappingError(f"POS field {field!r} must be a UUID or null.") from exc


def _date(value: Mapping[str, object], field: str) -> date:
    raw = _string(value, field)
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise POSResponseMappingError(f"POS field {field!r} must be an ISO date.") from exc


def _time(value: Mapping[str, object], field: str) -> time:
    raw = _string(value, field)
    try:
        return time.fromisoformat(raw)
    except ValueError as exc:
        raise POSResponseMappingError(f"POS field {field!r} must be an ISO time.") from exc


def _decimal(value: Mapping[str, object], field: str) -> Decimal:
    raw = _required(value, field)
    if isinstance(raw, bool) or not isinstance(raw, (str, int)):
        raise POSResponseMappingError(
            f"POS field {field!r} must be an exact decimal string or integer."
        )
    try:
        return Decimal(str(raw))
    except InvalidOperation as exc:
        raise POSResponseMappingError(f"POS field {field!r} must be decimal.") from exc


def _course_type(value: Mapping[str, object], field: str) -> CourseType:
    raw = _string(value, field)
    try:
        return CourseType(raw)
    except ValueError as exc:
        raise POSResponseMappingError(
            f"POS field {field!r} contains an unknown course type."
        ) from exc
