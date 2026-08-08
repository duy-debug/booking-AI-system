"""Tests for outcome-based booking handlers introduced by the migration."""

from datetime import date, time
from decimal import Decimal
from typing import cast
from uuid import UUID

import pytest

from app.application.handlers.check_customer_handler import CheckCustomerHandler
from app.application.handlers.search_course_handler import SearchCourseHandler
from app.application.handlers.select_booking_info_handler import (
    SelectBookingInfoHandler,
)
from app.application.handlers.select_schedule_handler import SelectScheduleHandler
from app.domain.booking_context import BookingContext
from app.domain.booking_models import (
    BookingGateway,
    Course,
    CourseSearchRequest,
    CustomerVerificationResult,
    Shop,
    TherapistPreference,
    TherapistPreferenceType,
)
from app.domain.outcomes import HandlerOutcome

SHOP = Shop(UUID("11111111-1111-1111-1111-111111111111"), "Komorebi")
COURSE = Course(
    UUID("22222222-2222-2222-2222-222222222222"),
    "Massage đá nóng",
    60,
    Decimal("500000"),
)


class CourseGateway:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    async def search_courses(self, request: CourseSearchRequest) -> list[Course]:
        if self.error is not None:
            raise self.error
        return [COURSE]


class CustomerGateway:
    async def verify_customer(self, request: object) -> CustomerVerificationResult:
        return CustomerVerificationResult("0901234567", "customer-1", None, 0, True, False, None)


def test_select_booking_info_updates_only_valid_values() -> None:
    handler = SelectBookingInfoHandler()
    context = BookingContext("conversation-1")

    invalid = handler.select_people(context, 4)
    selected = handler.select_duration(context, 60)

    assert invalid.outcome is HandlerOutcome.INVALID_INPUT
    assert invalid.error_code == "num_customer_too_many"
    assert context.num_customer is None
    assert selected.outcome is HandlerOutcome.SUCCESS
    assert selected.context_updates == {"duration_minutes": 60}
    assert context.duration_minutes is None


def test_select_date_rejects_last_unavailable_date_in_recovery() -> None:
    handler = SelectBookingInfoHandler()
    context = BookingContext(
        "conversation-1",
        last_unavailable_date=date(2026, 8, 9),
    )

    rejected = handler.select_date(context, date(2026, 8, 9))

    assert rejected.outcome is HandlerOutcome.INVALID_INPUT
    assert rejected.error_code == "date_still_unavailable"


def test_select_schedule_rejects_unverified_slot_and_group_therapist() -> None:
    handler = SelectScheduleHandler()
    context = BookingContext(
        "conversation-1",
        num_customer=2,
        available_slots=(time(10, 0),),
    )

    slot = handler.select_time(context, time(11, 0))
    therapist = handler.select_therapist(
        context,
        TherapistPreference(TherapistPreferenceType.PERSONAL, "therapist-1", "An"),
    )

    assert slot.outcome is HandlerOutcome.CONFLICT
    assert therapist.outcome is HandlerOutcome.INVALID_INPUT
    assert context.start_time is None
    assert context.therapist_preference is None


@pytest.mark.asyncio
async def test_search_course_returns_typed_outcomes() -> None:
    success = SearchCourseHandler(cast(BookingGateway, CourseGateway()))
    failure = SearchCourseHandler(
        cast(BookingGateway, CourseGateway(RuntimeError("POS unavailable")))
    )

    found = await success.execute(SHOP.shop_id, "massage")

    assert found.outcome is HandlerOutcome.SUCCESS
    assert found.data["courses"] == (COURSE,)
    with pytest.raises(RuntimeError, match="POS unavailable"):
        await failure.execute(SHOP.shop_id)


@pytest.mark.asyncio
async def test_check_customer_returns_updates_without_mutating_context() -> None:
    handler = CheckCustomerHandler(cast(BookingGateway, CustomerGateway()))
    context = BookingContext("conversation-1", shop=SHOP)

    checked = await handler.check(context, "0901234567", "Nguyễn An")
    assert checked.outcome is HandlerOutcome.SUCCESS
    assert checked.context_updates["phone"] == "0901234567"
    assert context.customer is None
    assert context.phone is None
