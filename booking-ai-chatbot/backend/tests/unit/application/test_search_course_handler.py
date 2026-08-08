"""Tests for the service search application handler."""

from datetime import date, time
from decimal import Decimal
from uuid import UUID

import pytest

from app.application.handlers.search_course_handler import SearchCourseHandler
from app.domain.booking_models import (
    AvailabilityRequest,
    AvailabilityWindowResult,
    Booking,
    BookingGateway,
    Course,
    CourseSearchRequest,
    CourseType,
    CreateBookingRequest,
    CreateBookingResult,
    CustomerVerificationRequest,
    CustomerVerificationResult,
    FinalAvailabilityRequest,
    FinalAvailabilityResult,
    InvalidBookingDataError,
    Shop,
)
from app.domain.outcomes import HandlerOutcome

SHOP_ID = UUID("11111111-1111-1111-1111-111111111111")
BOOKING_DATE = date(2026, 8, 1)
COURSE = Course(
    course_id=UUID("22222222-2222-2222-2222-222222222222"),
    name="Aromatherapy",
    duration_minutes=60,
    price=Decimal("500000.00"),
)


class FakeBookingGateway:
    """Booking gateway fake that records service searches."""

    def __init__(
        self,
        courses: list[Course],
        error: InvalidBookingDataError | None = None,
    ) -> None:
        self.courses = courses
        self.error = error
        self.search_courses_call_count = 0
        self.received_request: CourseSearchRequest | None = None

    async def search_shops(self, query: str | None = None) -> list[Shop]:
        raise AssertionError("Unexpected search_shops call.")

    async def search_courses(
        self,
        request: CourseSearchRequest,
    ) -> list[Course]:
        self.search_courses_call_count += 1
        self.received_request = request
        if self.error is not None:
            raise self.error
        return self.courses

    async def get_available_slots(
        self,
        request: AvailabilityRequest,
    ) -> AvailabilityWindowResult:
        raise AssertionError("Unexpected get_available_slots call.")

    async def verify_customer(
        self,
        request: CustomerVerificationRequest,
    ) -> CustomerVerificationResult:
        raise AssertionError("Unexpected verify_customer call.")

    async def check_final_availability(
        self,
        request: FinalAvailabilityRequest,
    ) -> FinalAvailabilityResult:
        raise AssertionError("Unexpected check_final_availability call.")

    async def create_booking(
        self,
        request: CreateBookingRequest,
    ) -> CreateBookingResult:
        raise AssertionError("Unexpected create_booking call.")

    async def lookup_booking(self, booking_id: UUID) -> Booking:
        raise AssertionError("Unexpected lookup_booking call.")

    async def reschedule_booking(
        self,
        booking_id: UUID,
        booking_date: date,
        start_time: time,
    ) -> Booking:
        raise AssertionError("Unexpected reschedule_booking call.")

    async def cancel_booking(self, booking_id: UUID) -> Booking:
        raise AssertionError("Unexpected cancel_booking call.")


def make_handler(fake: FakeBookingGateway) -> SearchCourseHandler:
    gateway: BookingGateway = fake
    return SearchCourseHandler(gateway)


@pytest.mark.asyncio
async def test_execute_maps_pos_request_and_filters_query_locally() -> None:
    other = Course(
        course_id=UUID("33333333-3333-3333-3333-333333333333"),
        name="Head spa",
        duration_minutes=30,
        price=Decimal("250000.00"),
    )
    courses = [COURSE, other]
    fake = FakeBookingGateway(courses)

    result = await make_handler(fake).execute(
        SHOP_ID,
        "  AROMA  ",
        course_type=CourseType.MAIN,
        is_active=True,
    )

    assert fake.search_courses_call_count == 1
    assert fake.received_request == CourseSearchRequest(
        shop_id=SHOP_ID,
        course_type=CourseType.MAIN,
        is_active=True,
    )
    assert result.outcome is HandlerOutcome.SUCCESS
    assert result.data["courses"] == (COURSE,)


@pytest.mark.asyncio
async def test_execute_prefers_exact_name_over_broader_substring_matches() -> None:
    longer = Course(
        course_id=UUID("33333333-3333-3333-3333-333333333333"),
        name=f"{COURSE.name} 90 phút",
        duration_minutes=90,
        price=Decimal("650000.00"),
    )
    fake = FakeBookingGateway([COURSE, longer])

    result = await make_handler(fake).execute(SHOP_ID, COURSE.name)

    assert result.data["courses"] == (COURSE,)


@pytest.mark.asyncio
async def test_execute_without_query_returns_original_gateway_list() -> None:
    courses = [COURSE]
    fake = FakeBookingGateway(courses)

    result = await make_handler(fake).execute(SHOP_ID)

    assert fake.search_courses_call_count == 1
    assert fake.received_request == CourseSearchRequest(shop_id=SHOP_ID)
    assert result.data["courses"] == tuple(courses)


@pytest.mark.asyncio
async def test_execute_returns_same_empty_list_from_gateway() -> None:
    courses: list[Course] = []
    fake = FakeBookingGateway(courses)

    result = await make_handler(fake).execute(SHOP_ID)

    assert result.outcome is HandlerOutcome.SUCCESS
    assert result.data["courses"] == ()


@pytest.mark.asyncio
async def test_execute_propagates_domain_exception() -> None:
    error = InvalidBookingDataError("Invalid service search.")
    fake = FakeBookingGateway([], error=error)

    with pytest.raises(InvalidBookingDataError) as exc_info:
        await make_handler(fake).execute(SHOP_ID, "invalid")

    assert exc_info.value is error
    assert fake.search_courses_call_count == 1
