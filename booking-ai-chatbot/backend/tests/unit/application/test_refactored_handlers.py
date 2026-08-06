"""Tests for outcome-based booking handlers introduced by the migration."""

from datetime import time
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
        return CustomerVerificationResult(
            "0901234567", "customer-1", None, 0, True, False, None
        )


def test_select_booking_info_updates_only_valid_values() -> None:
    handler = SelectBookingInfoHandler()
    context = BookingContext("conversation-1")

    invalid = handler.select_people(context, 4)
    selected = handler.select_duration(context, 60)

    assert invalid.outcome is HandlerOutcome.INVALID_INPUT
    assert context.num_customer is None
    assert selected.outcome is HandlerOutcome.SUCCESS
    assert context.duration_minutes == 60


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

    found = await success.handle(SHOP.shop_id, "massage", duration_minutes=60)
    unavailable = await failure.handle(SHOP.shop_id)

    assert found.outcome is HandlerOutcome.SUCCESS
    assert found.data["courses"] == (COURSE,)
    assert unavailable.outcome is HandlerOutcome.EXTERNAL_FAILURE


@pytest.mark.asyncio
async def test_check_customer_commits_only_after_success() -> None:
    handler = CheckCustomerHandler(cast(BookingGateway, CustomerGateway()))
    context = BookingContext("conversation-1", shop=SHOP)

    checked = await handler.check(context, "0901234567", "Nguyễn An")
    confirmed = handler.confirm(context)

    assert checked.outcome is HandlerOutcome.SUCCESS
    assert confirmed.outcome is HandlerOutcome.SUCCESS
    assert context.customer_name == "Nguyễn An"
    assert context.phone_confirmed is True
