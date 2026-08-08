"""Contract tests for the verified HTTP booking gateway operations."""

import json
import logging
from collections.abc import Callable
from datetime import date, time
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

import httpx
import pytest

from app.domain.booking_models import (
    AvailabilityRequest,
    AvailabilityWindowResult,
    AvailableTherapistRequest,
    BookingGateway,
    CourseSearchRequest,
    CourseType,
    CreateBookingRequest,
    CustomerNotAllowedError,
    CustomerVerificationRequest,
    FinalAvailabilityRequest,
    POSAuthenticationError,
    POSAuthorizationError,
    POSConflictError,
    POSConnectionError,
    POSContractNotConfiguredError,
    POSNotFoundError,
    POSResponseMappingError,
    POSTemporaryError,
    POSTimeoutError,
    POSValidationError,
    SlotConflictError,
    TherapistPreference,
    TherapistPreferenceType,
)
from app.infrastructure.pos_api_client import PosApiClient

SHOP_ID = UUID("550e8400-e29b-41d4-a716-446655440001")
MAIN_COURSE_ID = UUID("550e8400-e29b-41d4-a716-446655440101")
ADDON_COURSE_ID = UUID("550e8400-e29b-41d4-a716-446655440102")
THERAPIST_ID = UUID("550e8400-e29b-41d4-a716-446655440201")
BOOKING_ID = UUID("550e8400-e29b-41d4-a716-446655440501")
BOOKING_DATE = date(2026, 7, 20)
RESERVATION_IDS = (
    UUID("550e8400-e29b-41d4-a716-446655440601"),
    UUID("550e8400-e29b-41d4-a716-446655440602"),
)


def _slot(
    start: str = "10:00",
    *,
    available: bool = True,
    reason_code: str | None = None,
    message: str | None = None,
) -> dict[str, object]:
    return {
        "start_time": start,
        "end_time": "11:15",
        "duration_minutes": 75,
        "available": available,
        "reason_code": reason_code,
        "message": message,
        "available_therapist_count": 1 if available else 0,
        "required_therapist_count": 1,
    }


def _availability_payload(data: list[dict[str, object]]) -> dict[str, object]:
    return {
        "data": data,
        "meta": {
            "booking_date": BOOKING_DATE.isoformat(),
            "shop_id": str(SHOP_ID),
            "number_of_people": 1,
        },
    }


def _availability_request(
    preference: TherapistPreference | None = None,
) -> AvailabilityRequest:
    return AvailabilityRequest(
        shop_id=SHOP_ID,
        booking_date=BOOKING_DATE,
        num_customer=1,
        duration_minutes=75,
        main_course_id=MAIN_COURSE_ID,
        addon_ids=(ADDON_COURSE_ID,),
        therapist_preference=preference,
    )


def _course_payload() -> dict[str, object]:
    return {
        "data": [
            {
                "course_id": str(MAIN_COURSE_ID),
                "shop_id": str(SHOP_ID),
                "name": "Body Massage",
                "duration_minutes": 60,
                "price": "6000.00",
                "course_type": "main",
            },
            {
                "course_id": str(ADDON_COURSE_ID),
                "shop_id": str(SHOP_ID),
                "name": "Head Spa",
                "duration_minutes": 15,
                "price": "1500.00",
                "course_type": "addon",
            },
        ]
    }


def _eligibility_payload(
    customer: dict[str, object] | None,
) -> dict[str, object]:
    return {
        "data": {
            "check_id": "550e8400-e29b-41d4-a716-446655440401",
            "phone": "0901234567",
            "eligible": True,
            "customer": customer,
            "restriction": None,
        }
    }


def _create_request(
    preference: TherapistPreference | None = None,
    *,
    num_customer: int = 1,
) -> CreateBookingRequest:
    return CreateBookingRequest(
        shop_id=SHOP_ID,
        booking_date=BOOKING_DATE,
        start_time=time(10, 0),
        num_customer=num_customer,
        duration_minutes=75,
        main_course_id=MAIN_COURSE_ID,
        addon_ids=(ADDON_COURSE_ID,),
        therapist_preference=preference,
        phone="0901234567",
        customer_name="Nguyen An",
        member_rank="gold",
        idempotency_key="7d9f1c8e-1111-2222-3333-123456789abc",
    )


def _create_payload(
    *,
    num_customer: int = 1,
    therapist_type: str = "none",
    therapist_id: UUID | None = None,
    therapist_gender: str | None = None,
) -> dict[str, object]:
    courses = [
        {
            "course_id": str(MAIN_COURSE_ID),
            "course_role": "main",
            "course_name_snapshot": "Body Massage",
            "duration_snapshot": 60,
            "price_snapshot": "6000.00",
        },
        {
            "course_id": str(ADDON_COURSE_ID),
            "course_role": "addon",
            "course_name_snapshot": "Head Spa",
            "duration_snapshot": 15,
            "price_snapshot": "1500.00",
        },
    ]
    reservations = [
        {
            "reservation_id": str(RESERVATION_IDS[index]),
            "person_index": index + 1,
            "therapist_id": str(THERAPIST_ID),
            "therapist_name": "Yuki",
            "start_time": "10:00:00",
            "end_time": "11:15:00",
            "status": "assigned",
            "assignment_source": "auto",
            "courses": courses,
        }
        for index in range(num_customer)
    ]
    return {
        "data": {
            "booking_id": str(BOOKING_ID),
            "booking_code": "KMB-20260720-ABCDEFGH",
            "shop_id": str(SHOP_ID),
            "shop_name": "Komorebi",
            "customer_id": "550e8400-e29b-41d4-a716-446655440301",
            "booking_date": BOOKING_DATE.isoformat(),
            "start_time": "10:00:00",
            "end_time": "11:15:00",
            "number_of_people": num_customer,
            "total_duration_minutes": 75,
            "status": "confirmed",
            "therapist_request_type": therapist_type,
            "requested_therapist_id": (str(therapist_id) if therapist_id is not None else None),
            "requested_gender": therapist_gender,
            "cancel_reason": None,
            "cancelled_at": None,
            "created_at": "2026-07-01T10:00:00",
            "updated_at": "2026-07-01T10:00:00",
            "reservations": reservations,
        }
    }


def _gateway(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    timeout_seconds: float | None = None,
) -> tuple[httpx.AsyncClient, PosApiClient]:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    gateway = PosApiClient(
        client=client,
        base_url="https://pos.example/",
        timeout_seconds=timeout_seconds,
    )
    return client, gateway


def _request_body(request: httpx.Request) -> dict[str, Any]:
    payload = json.loads(request.content)
    assert isinstance(payload, dict)
    return cast(dict[str, Any], payload)


def test_rejects_empty_base_url_and_invalid_timeout() -> None:
    client = httpx.AsyncClient()
    with pytest.raises(ValueError, match="base URL"):
        PosApiClient(client=client, base_url="  ")
    with pytest.raises(ValueError, match="timeout"):
        PosApiClient(client=client, base_url="https://pos.example", timeout_seconds=0)


@pytest.mark.asyncio
async def test_protocol_assignment_and_default_shop_search_contract() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "shop_id": str(SHOP_ID),
                        "shop_code": "SHOP001",
                        "name": "Komorebi",
                        "address": None,
                        "phone": "0900000000",
                        "links": {
                            "self": f"/api/shops/{SHOP_ID}",
                            "courses": f"/api/shops/{SHOP_ID}/courses",
                            "available_slots": f"/api/shops/{SHOP_ID}/available-slots",
                        },
                    }
                ],
                "meta": {"total": 1, "limit": None, "next_cursor": None},
            },
        )

    client, concrete_gateway = _gateway(handler)
    gateway: BookingGateway = concrete_gateway
    try:
        shops = await gateway.search_shops()
    finally:
        await client.aclose()

    assert len(requests) == 1
    assert requests[0].method == "GET"
    assert requests[0].url.path == "/api/shops"
    assert requests[0].url.query == b""
    assert shops[0].shop_id == SHOP_ID
    assert shops[0].name == "Komorebi"
    assert shops[0].address is None
    assert shops[0].phone == "0900000000"


@pytest.mark.asyncio
async def test_shop_keyword_is_blocked_without_an_http_request() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(500)

    client, gateway = _gateway(handler)
    try:
        with pytest.raises(POSContractNotConfiguredError, match="keyword"):
            await gateway.search_shops("Tokyo")
    finally:
        await client.aclose()

    assert requests == []


@pytest.mark.asyncio
async def test_shop_response_requires_declared_fields() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{}], "meta": {"total": 1}})

    client, gateway = _gateway(handler)
    try:
        with pytest.raises(POSResponseMappingError, match="shop_id"):
            await gateway.search_shops()
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_success_with_invalid_json_is_a_response_mapping_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-json")

    client, gateway = _gateway(handler)
    try:
        with pytest.raises(POSResponseMappingError, match="invalid JSON"):
            await gateway.search_shops()
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_availability_sends_complete_none_preference_query_and_preserves_order() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json=_availability_payload(
                [
                    _slot("10:00"),
                    _slot("10:15", available=False, reason_code="SLOT_CONFLICT"),
                    _slot("10:30"),
                ]
            ),
        )

    client, gateway = _gateway(handler, timeout_seconds=2.5)
    try:
        result = await gateway.get_available_slots(_availability_request())
    finally:
        await client.aclose()

    assert result == AvailabilityWindowResult(
        slots=(time(10, 0), time(10, 30)),
        status="available",
    )
    assert len(requests) == 1
    request = requests[0]
    assert request.method == "GET"
    assert request.url.path == f"/api/shops/{SHOP_ID}/available-slots"
    assert dict(request.url.params) == {
        "booking_date": "2026-07-20",
        "number_of_people": "1",
        "main_course_id": str(MAIN_COURSE_ID),
        "therapist_request_type": "none",
        "addon_course_ids": str(ADDON_COURSE_ID),
    }
    timeout = request.extensions["timeout"]
    assert isinstance(timeout, dict)
    assert timeout["read"] == 2.5


@pytest.mark.asyncio
async def test_available_therapist_response_maps_name_and_uuid() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == f"/api/shops/{SHOP_ID}/available-therapists"
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "therapist_id": str(THERAPIST_ID),
                        "shop_id": str(SHOP_ID),
                        "name": "Nguyen Lan",
                        "gender": "female",
                        "available": True,
                    }
                ]
            },
        )

    client, gateway = _gateway(handler)
    try:
        result = await gateway.search_available_therapists(
            AvailableTherapistRequest(
                shop_id=SHOP_ID,
                booking_date=BOOKING_DATE,
                start_time=time(10, 0),
                end_time=time(11, 15),
            )
        )
    finally:
        await client.aclose()

    assert result == [
        TherapistPreference(
            TherapistPreferenceType.PERSONAL,
            therapist_id=str(THERAPIST_ID),
            therapist_name="Nguyen Lan",
        )
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("preference", "expected_query"),
    [
        (
            TherapistPreference(TherapistPreferenceType.FEMALE),
            {"therapist_request_type": "gender", "therapist_gender": "female"},
        ),
        (
            TherapistPreference(
                TherapistPreferenceType.PERSONAL,
                therapist_id=str(THERAPIST_ID),
            ),
            {"therapist_request_type": "specific", "therapist_id": str(THERAPIST_ID)},
        ),
    ],
)
async def test_availability_maps_supported_therapist_preferences(
    preference: TherapistPreference,
    expected_query: dict[str, str],
) -> None:
    observed: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed.update(dict(request.url.params))
        return httpx.Response(200, json=_availability_payload([_slot()]))

    client, gateway = _gateway(handler)
    try:
        await gateway.get_available_slots(_availability_request(preference))
    finally:
        await client.aclose()

    for key, value in expected_query.items():
        assert observed[key] == value


@pytest.mark.asyncio
async def test_personal_preference_by_name_is_blocked_without_request() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(500)

    preference = TherapistPreference(
        TherapistPreferenceType.PERSONAL,
        therapist_name="Yuki",
    )
    client, gateway = _gateway(handler)
    try:
        with pytest.raises(POSContractNotConfiguredError, match="by name"):
            await gateway.get_available_slots(_availability_request(preference))
    finally:
        await client.aclose()

    assert requests == []


@pytest.mark.asyncio
async def test_empty_availability_is_distinct_from_malformed_response() -> None:
    responses = iter(
        [
            httpx.Response(200, json=_availability_payload([])),
            httpx.Response(
                200,
                json=_availability_payload([_slot(start="not-a-time")]),
            ),
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return next(responses)

    client, gateway = _gateway(handler)
    try:
        assert await gateway.get_available_slots(
            _availability_request()
        ) == AvailabilityWindowResult(slots=(), status="no_slots_available")
        with pytest.raises(POSResponseMappingError, match="ISO time"):
            await gateway.get_available_slots(_availability_request())
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_availability_preserves_no_working_shift_semantic() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                **_availability_payload([]),
                "availability_status": "no_working_shift",
            },
        )

    client, gateway = _gateway(handler)
    try:
        result = await gateway.get_available_slots(_availability_request())
    finally:
        await client.aclose()

    assert result == AvailabilityWindowResult(slots=(), status="no_working_shift")


@pytest.mark.asyncio
async def test_availability_maps_rfc9457_not_found_without_exposing_detail() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404,
            json={
                "status": 404,
                "code": "SHOP_NOT_FOUND",
                "detail": "sensitive backend detail",
            },
        )

    client, gateway = _gateway(handler)
    try:
        with pytest.raises(POSNotFoundError) as captured:
            await gateway.get_available_slots(_availability_request())
    finally:
        await client.aclose()

    assert captured.value.status_code == 404
    assert captured.value.code == "SHOP_NOT_FOUND"
    assert "sensitive backend detail" not in str(captured.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "expected_error"),
    [
        (400, POSValidationError),
        (401, POSAuthenticationError),
        (403, POSAuthorizationError),
        (409, POSConflictError),
        (422, POSValidationError),
        (429, POSTemporaryError),
        (503, POSTemporaryError),
    ],
)
async def test_documented_http_statuses_map_to_typed_errors(
    status_code: int,
    expected_error: type[Exception],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code,
            json={"status": status_code, "code": "SANITIZED_ERROR", "detail": "detail"},
        )

    client, gateway = _gateway(handler)
    try:
        with pytest.raises(expected_error):
            await gateway.get_available_slots(_availability_request())
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_final_availability_sends_selected_time_and_maps_conflict() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json=_availability_payload(
                [
                    _slot(
                        "10:00",
                        available=False,
                        reason_code="SLOT_CONFLICT",
                        message="Slot is no longer available.",
                    )
                ]
            ),
        )

    request = FinalAvailabilityRequest(
        shop_id=SHOP_ID,
        booking_date=BOOKING_DATE,
        start_time=time(10, 0),
        num_customer=1,
        duration_minutes=75,
        main_course_id=MAIN_COURSE_ID,
        addon_ids=(ADDON_COURSE_ID,),
    )
    client, gateway = _gateway(handler)
    try:
        result = await gateway.check_final_availability(request)
    finally:
        await client.aclose()

    assert result.available is False
    assert result.reason == "SLOT_CONFLICT"
    assert result.nearest_slots == ()
    assert len(requests) == 1
    assert requests[0].url.params["start_time"] == "10:00"


@pytest.mark.asyncio
async def test_network_timeout_and_connection_failures_are_typed() -> None:
    timeout_request_count = 0

    def timeout_handler(request: httpx.Request) -> httpx.Response:
        nonlocal timeout_request_count
        timeout_request_count += 1
        raise httpx.ReadTimeout("timed out", request=request)

    timeout_client, timeout_gateway = _gateway(timeout_handler)
    try:
        with pytest.raises(POSTimeoutError):
            await timeout_gateway.get_available_slots(_availability_request())
    finally:
        await timeout_client.aclose()
    assert timeout_request_count == 1

    connection_request_count = 0

    def connection_handler(request: httpx.Request) -> httpx.Response:
        nonlocal connection_request_count
        connection_request_count += 1
        raise httpx.ConnectError("connection failed", request=request)

    connection_client, connection_gateway = _gateway(connection_handler)
    try:
        with pytest.raises(POSConnectionError):
            await connection_gateway.get_available_slots(_availability_request())
    finally:
        await connection_client.aclose()
    assert connection_request_count == 1


@pytest.mark.asyncio
async def test_search_courses_sends_only_pos_filters_and_maps_course_types(
    caplog: pytest.LogCaptureFixture,
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=_course_payload())

    client, gateway = _gateway(handler)
    try:
        with caplog.at_level(
            logging.INFO,
            logger="app.infrastructure.pos_api_client",
        ):
            courses = await gateway.search_courses(
                CourseSearchRequest(
                    shop_id=SHOP_ID,
                    course_type=CourseType.MAIN,
                    is_active=False,
                )
            )
    finally:
        await client.aclose()

    assert len(requests) == 1
    assert requests[0].method == "GET"
    assert requests[0].url.path == f"/api/shops/{SHOP_ID}/courses"
    assert dict(requests[0].url.params) == {
        "course_type": "main",
        "is_active": "false",
    }
    assert "booking_date" not in requests[0].url.params
    assert "query" not in requests[0].url.params
    assert courses[0].course_type is CourseType.MAIN
    assert courses[1].course_type is CourseType.ADDON
    assert courses[0].duration_minutes == 60
    assert courses[0].price == Decimal("6000.00")
    assert "[PosApiClient] pos_api_completed" in caplog.text
    assert "operation=search_courses" in caplog.text
    assert "status_code=200" in caplog.text
    assert "item_count=2" in caplog.text


@pytest.mark.asyncio
async def test_search_courses_maps_not_found_and_malformed_success(
    caplog: pytest.LogCaptureFixture,
) -> None:
    responses = iter(
        [
            httpx.Response(404, json={"code": "SHOP_NOT_FOUND"}),
            httpx.Response(200, json={"data": [{"course_id": "invalid"}]}),
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return next(responses)

    client, gateway = _gateway(handler)
    request = CourseSearchRequest(shop_id=SHOP_ID)
    try:
        with caplog.at_level(
            logging.WARNING,
            logger="app.infrastructure.pos_api_client",
        ):
            with pytest.raises(POSNotFoundError):
                await gateway.search_courses(request)
        with pytest.raises(POSResponseMappingError):
            await gateway.search_courses(request)
    finally:
        await client.aclose()
    assert "error_code=SHOP_NOT_FOUND" in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("customer", "expected_id", "expected_rank", "expected_visits"),
    [
        (
            {
                "customer_type": "existing",
                "customer_id": "550e8400-e29b-41d4-a716-446655440301",
                "name": "Nguyen An",
                "is_member": True,
                "member_rank": "gold",
                "visit_count": 12,
            },
            "550e8400-e29b-41d4-a716-446655440301",
            "gold",
            12,
        ),
        (None, None, None, None),
    ],
)
async def test_verify_customer_maps_existing_and_new_customer_semantics(
    customer: dict[str, object] | None,
    expected_id: str | None,
    expected_rank: str | None,
    expected_visits: int | None,
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json=_eligibility_payload(customer))

    client, gateway = _gateway(handler)
    verification_request = CustomerVerificationRequest(
        shop_id=SHOP_ID,
        phone="0901234567",
    )
    try:
        result = await gateway.verify_customer(verification_request)
    finally:
        await client.aclose()

    assert len(requests) == 1
    assert requests[0].method == "POST"
    assert requests[0].url.path == "/api/booking-eligibility-checks"
    assert _request_body(requests[0]) == {
        "shop_id": str(SHOP_ID),
        "phone": "0901234567",
    }
    assert result.customer_id == expected_id
    assert result.member_rank == expected_rank
    assert result.visit_count == expected_visits
    assert result.ng_list_checked is True
    assert result.is_ng_customer is False


@pytest.mark.asyncio
async def test_verify_customer_rejects_missing_eligibility_and_maps_ng_block() -> None:
    missing = _eligibility_payload(None)
    del cast(dict[str, object], missing["data"])["eligible"]
    responses = iter(
        [
            httpx.Response(201, json=missing),
            httpx.Response(403, json={"code": "CUSTOMER_IN_NG_LIST"}),
            httpx.Response(404, json={"code": "SHOP_NOT_FOUND"}),
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return next(responses)

    client, gateway = _gateway(handler)
    request = CustomerVerificationRequest(SHOP_ID, "0901234567")
    try:
        with pytest.raises(POSResponseMappingError, match="eligible"):
            await gateway.verify_customer(request)
        with pytest.raises(CustomerNotAllowedError):
            await gateway.verify_customer(request)
        with pytest.raises(POSNotFoundError):
            await gateway.verify_customer(request)
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_verify_customer_timeout_makes_exactly_one_request() -> None:
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        raise httpx.ReadTimeout("timed out", request=request)

    client, gateway = _gateway(handler)
    try:
        with pytest.raises(POSTimeoutError):
            await gateway.verify_customer(CustomerVerificationRequest(SHOP_ID, "0901234567"))
    finally:
        await client.aclose()

    assert request_count == 1


@pytest.mark.asyncio
async def test_create_booking_sends_exact_payload_and_maps_child_reservations() -> None:
    requests: list[httpx.Request] = []
    preference = TherapistPreference(TherapistPreferenceType.NONE)

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json=_create_payload())

    client, gateway = _gateway(handler)
    create_request = _create_request(preference)
    try:
        result = await gateway.create_booking(create_request)
    finally:
        await client.aclose()

    assert len(requests) == 1
    request = requests[0]
    assert request.method == "POST"
    assert request.url.path == "/api/bookings"
    assert request.headers["Idempotency-Key"] == create_request.idempotency_key
    body = _request_body(request)
    assert "idempotency_key" not in body
    assert body == {
        "shop_id": str(SHOP_ID),
        "booking_date": "2026-07-20",
        "start_time": "10:00",
        "number_of_people": 1,
        "customer": {"phone": "0901234567", "name": "Nguyen An"},
        "courses": [
            {"course_id": str(MAIN_COURSE_ID), "course_role": "main"},
            {"course_id": str(ADDON_COURSE_ID), "course_role": "addon"},
        ],
        "confirmed_by_customer": True,
        "therapist_request": {"type": "none"},
    }
    assert result.booking.booking_id == BOOKING_ID
    assert result.booking.status == "confirmed"
    assert result.booking.customer.phone == create_request.phone
    assert result.booking.customer.name == create_request.customer_name
    assert result.booking.main_course.course_id == MAIN_COURSE_ID
    assert result.booking.addons[0].course_id == ADDON_COURSE_ID
    assert result.child_reservations[0].reservation_id == RESERVATION_IDS[0]
    assert result.child_reservations[0].participant_index == 1
    assert result.reservation_code == "KMB-20260720-ABCDEFGH"
    assert result.booking.reservation_code == "KMB-20260720-ABCDEFGH"
    assert result.reservation_codes == ()


@pytest.mark.asyncio
async def test_group_create_preserves_every_child_reservation_id() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json=_create_payload(num_customer=2))

    client, gateway = _gateway(handler)
    try:
        result = await gateway.create_booking(_create_request(num_customer=2))
    finally:
        await client.aclose()

    assert result.booking.num_customer == 2
    assert tuple(item.reservation_id for item in result.child_reservations) == (RESERVATION_IDS)
    assert tuple(item.participant_index for item in result.child_reservations) == (1, 2)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("preference", "response_kwargs", "expected_request"),
    [
        (
            TherapistPreference(TherapistPreferenceType.FEMALE),
            {"therapist_type": "gender", "therapist_gender": "female"},
            {"type": "gender", "gender": "female"},
        ),
        (
            TherapistPreference(
                TherapistPreferenceType.PERSONAL,
                therapist_id=str(THERAPIST_ID),
            ),
            {"therapist_type": "specific", "therapist_id": THERAPIST_ID},
            {"type": "specific", "therapist_id": str(THERAPIST_ID)},
        ),
    ],
)
async def test_create_maps_gender_and_personal_therapist(
    preference: TherapistPreference,
    response_kwargs: dict[str, Any],
    expected_request: dict[str, str],
) -> None:
    observed: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed.update(_request_body(request))
        return httpx.Response(201, json=_create_payload(**response_kwargs))

    client, gateway = _gateway(handler)
    try:
        await gateway.create_booking(_create_request(preference))
    finally:
        await client.aclose()

    assert observed["therapist_request"] == expected_request


@pytest.mark.asyncio
async def test_create_blocks_personal_therapist_name_before_http() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(500)

    preference = TherapistPreference(
        TherapistPreferenceType.PERSONAL,
        therapist_name="Yuki",
    )
    client, gateway = _gateway(handler)
    try:
        with pytest.raises(POSContractNotConfiguredError, match="by name"):
            await gateway.create_booking(_create_request(preference))
    finally:
        await client.aclose()

    assert requests == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "code", "expected_error"),
    [
        (409, "SLOT_CONFLICT", SlotConflictError),
        (403, "CUSTOMER_IN_NG_LIST", CustomerNotAllowedError),
        (422, "INVALID_COURSE_COMBO", POSValidationError),
        (503, "POS_TEMPORARY_ERROR", POSTemporaryError),
    ],
)
async def test_create_maps_business_errors_once_without_retry(
    status: int,
    code: str,
    expected_error: type[Exception],
) -> None:
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(status, json={"code": code})

    client, gateway = _gateway(handler)
    try:
        with pytest.raises(expected_error):
            await gateway.create_booking(_create_request())
    finally:
        await client.aclose()

    assert request_count == 1


@pytest.mark.asyncio
async def test_create_timeout_and_malformed_success_do_not_retry() -> None:
    request_count = 0

    def timeout_handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        raise httpx.ReadTimeout("timed out", request=request)

    timeout_client, timeout_gateway = _gateway(timeout_handler)
    try:
        with pytest.raises(POSTimeoutError):
            await timeout_gateway.create_booking(_create_request())
    finally:
        await timeout_client.aclose()
    assert request_count == 1

    def malformed_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json={"data": {"booking_id": str(BOOKING_ID)}})

    malformed_client, malformed_gateway = _gateway(malformed_handler)
    try:
        with pytest.raises(POSResponseMappingError):
            await malformed_gateway.create_booking(_create_request())
    finally:
        await malformed_client.aclose()


@pytest.mark.asyncio
async def test_blocked_operations_never_call_unverified_endpoints() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(500)

    gateway_client, gateway = _gateway(handler)
    try:
        calls: list[Callable[[], Any]] = [
            lambda: gateway.lookup_booking(BOOKING_ID),
            lambda: gateway.reschedule_booking(BOOKING_ID, BOOKING_DATE, time(14, 0)),
            lambda: gateway.cancel_booking(BOOKING_ID),
        ]
        for call in calls:
            with pytest.raises(POSContractNotConfiguredError):
                await call()
    finally:
        await gateway_client.aclose()

    assert requests == []
