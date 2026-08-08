"""Tests for the shop search application handler."""

from datetime import date, time
from decimal import Decimal
from typing import cast
from uuid import UUID

import pytest

from app.application.handlers.search_shop_handler import SearchShopHandler
from app.domain.booking_models import (
    AvailabilityRequest,
    AvailabilityWindowResult,
    Booking,
    BookingGateway,
    Course,
    CourseSearchRequest,
    CourseType,
    InvalidBookingDataError,
    Shop,
    ShopSearchCriteria,
    ShopTherapist,
)
from app.domain.outcomes import HandlerOutcome

SHOP_A = Shop(
    shop_id=UUID("11111111-1111-1111-1111-111111111111"),
    name="Komorebi Ba Đình",
    address="Hà Nội",
)
SHOP_B = Shop(
    shop_id=UUID("22222222-2222-2222-2222-222222222222"),
    name="Komorebi Bình Thạnh",
    address="Hồ Chí Minh",
)
SHOP_C = Shop(
    shop_id=UUID("33333333-3333-3333-3333-333333333333"),
    name="Komorebi Cần Thơ",
    address="Cần Thơ",
)
MASSAGE_60_A = Course(
    course_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
    name="Massage đá nóng 60 phút",
    duration_minutes=60,
    price=Decimal("500000"),
)
MASSAGE_60_B = Course(
    course_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
    name="Massage đá nóng 60 phút",
    duration_minutes=60,
    price=Decimal("500000"),
)
MASSAGE_90_C = Course(
    course_id=UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
    name="Massage đá nóng 90 phút",
    duration_minutes=90,
    price=Decimal("700000"),
)
ADDON_HEAD_A = Course(
    course_id=UUID("dddddddd-dddd-dddd-dddd-dddddddddddd"),
    name="Chăm sóc da đầu thư giãn",
    duration_minutes=15,
    price=Decimal("100000"),
    course_type=CourseType.ADDON,
)
THERAPIST_MAI_A = ShopTherapist(
    therapist_id=UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"),
    shop_id=SHOP_A.shop_id,
    name="Mai",
    gender="female",
)
THERAPIST_LAN_B = ShopTherapist(
    therapist_id=UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"),
    shop_id=SHOP_B.shop_id,
    name="Lan",
    gender="female",
)


class FakeBookingGateway:
    """Booking gateway fake that records shop and availability lookups."""

    def __init__(
        self,
        shops: list[Shop],
        *,
        courses_by_shop: dict[UUID, tuple[Course, ...]] | None = None,
        slots_by_shop: dict[UUID, tuple[time, ...]] | None = None,
        error: InvalidBookingDataError | None = None,
    ) -> None:
        self.shops = shops
        self.courses_by_shop = courses_by_shop or {}
        self.slots_by_shop = slots_by_shop or {}
        self.error = error
        self.search_shops_call_count = 0
        self.search_courses_calls: list[CourseSearchRequest] = []
        self.availability_calls: list[AvailabilityRequest] = []

    async def search_shops(self, query: str | None = None) -> list[Shop]:
        self.search_shops_call_count += 1
        if query is not None:
            raise AssertionError("Shop query must be filtered locally from the POS catalog.")
        if self.error is not None:
            raise self.error
        return self.shops

    async def search_courses(
        self,
        request: CourseSearchRequest,
    ) -> list[Course]:
        self.search_courses_calls.append(request)
        courses = self.courses_by_shop.get(request.shop_id, ())
        if request.course_type is None:
            return list(courses)
        return [course for course in courses if course.course_type is request.course_type]

    async def get_available_slots(
        self,
        request: AvailabilityRequest,
    ) -> AvailabilityWindowResult:
        self.availability_calls.append(request)
        return AvailabilityWindowResult(self.slots_by_shop.get(request.shop_id, ()))

    async def create_booking(self, request: object) -> object:
        raise AssertionError("Unexpected create_booking call.")

    async def verify_customer(self, request: object) -> object:
        raise AssertionError("Unexpected verify_customer call.")

    async def check_final_availability(self, request: object) -> object:
        raise AssertionError("Unexpected check_final_availability call.")

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


class FakeTherapistCatalogGateway:
    def __init__(self, therapists_by_shop: dict[UUID, tuple[ShopTherapist, ...]]) -> None:
        self.therapists_by_shop = therapists_by_shop
        self.calls: list[UUID] = []

    async def search_shop_therapists(
        self,
        shop_id: UUID,
        *,
        is_active: bool = True,
    ) -> list[ShopTherapist]:
        self.calls.append(shop_id)
        return list(self.therapists_by_shop.get(shop_id, ()))


def make_handler(
    fake: FakeBookingGateway,
    *,
    therapists: FakeTherapistCatalogGateway | None = None,
) -> SearchShopHandler:
    return SearchShopHandler(
        cast(BookingGateway, fake),
        therapist_catalog_gateway=therapists,
    )


@pytest.mark.asyncio
async def test_execute_returns_all_eligible_shops_without_display_cap() -> None:
    fake = FakeBookingGateway([SHOP_A, SHOP_B, SHOP_C])

    result = await make_handler(fake).execute()

    assert result.outcome is HandlerOutcome.SUCCESS
    assert result.data["shops"] == (SHOP_A, SHOP_B, SHOP_C)
    assert fake.availability_calls == []


@pytest.mark.asyncio
async def test_execute_filters_by_requested_service_across_all_shops() -> None:
    fake = FakeBookingGateway(
        [SHOP_A, SHOP_B, SHOP_C],
        courses_by_shop={
            SHOP_A.shop_id: (MASSAGE_60_A,),
            SHOP_B.shop_id: (MASSAGE_60_B,),
            SHOP_C.shop_id: (MASSAGE_90_C,),
        },
    )

    result = await make_handler(fake).execute(
        criteria=ShopSearchCriteria(requested_main_course_name="Massage đá nóng 60 phút")
    )

    assert result.outcome is HandlerOutcome.SUCCESS
    assert result.data["shops"] == (SHOP_A, SHOP_B)
    assert fake.availability_calls == []


@pytest.mark.asyncio
async def test_execute_filters_by_requested_therapist_owner_shop() -> None:
    fake = FakeBookingGateway([SHOP_A, SHOP_B])
    therapists = FakeTherapistCatalogGateway(
        {
            SHOP_A.shop_id: (THERAPIST_MAI_A,),
            SHOP_B.shop_id: (THERAPIST_LAN_B,),
        }
    )

    result = await make_handler(fake, therapists=therapists).execute(
        criteria=ShopSearchCriteria(requested_therapist_name="Lan")
    )

    assert result.outcome is HandlerOutcome.SUCCESS
    assert result.data["shops"] == (SHOP_B,)


@pytest.mark.asyncio
async def test_execute_returns_business_not_found_when_therapist_not_owned_by_any_shop() -> None:
    fake = FakeBookingGateway([SHOP_A])
    therapists = FakeTherapistCatalogGateway({SHOP_A.shop_id: (THERAPIST_MAI_A,)})

    result = await make_handler(fake, therapists=therapists).execute(
        criteria=ShopSearchCriteria(requested_therapist_name="Khánh")
    )

    assert result.outcome is HandlerOutcome.NOT_FOUND
    assert result.error_code == "therapist_not_supported_in_any_shop"


@pytest.mark.asyncio
async def test_execute_does_not_call_exact_availability_when_date_time_are_insufficient() -> None:
    fake = FakeBookingGateway(
        [SHOP_A, SHOP_B],
        courses_by_shop={
            SHOP_A.shop_id: (MASSAGE_60_A,),
            SHOP_B.shop_id: (MASSAGE_60_B,),
        },
    )

    result = await make_handler(fake).execute(
        criteria=ShopSearchCriteria(
            booking_date=date(2026, 8, 9),
            requested_start_time=time(19, 0),
            requested_main_course_name="Massage đá nóng 60 phút",
        )
    )

    assert result.outcome is HandlerOutcome.SUCCESS
    assert result.data["shops"] == (SHOP_A, SHOP_B)
    assert fake.availability_calls == []


@pytest.mark.asyncio
async def test_execute_uses_exact_availability_when_full_booking_constraints_are_known() -> None:
    fake = FakeBookingGateway(
        [SHOP_A, SHOP_B],
        courses_by_shop={
            SHOP_A.shop_id: (MASSAGE_60_A, ADDON_HEAD_A),
            SHOP_B.shop_id: (MASSAGE_60_B, ADDON_HEAD_A),
        },
        slots_by_shop={
            SHOP_A.shop_id: (time(10, 0),),
            SHOP_B.shop_id: (time(19, 0),),
        },
    )
    therapists = FakeTherapistCatalogGateway(
        {
            SHOP_A.shop_id: (THERAPIST_MAI_A,),
            SHOP_B.shop_id: (THERAPIST_LAN_B,),
        }
    )

    result = await make_handler(fake, therapists=therapists).execute(
        criteria=ShopSearchCriteria(
            booking_date=date(2026, 8, 9),
            requested_start_time=time(19, 0),
            num_customer=1,
            duration_minutes=60,
            requested_main_course_name="Massage đá nóng 60 phút",
            requested_therapist_name="Lan",
        )
    )

    assert result.outcome is HandlerOutcome.SUCCESS
    assert result.data["shops"] == (SHOP_B,)
    assert [call.shop_id for call in fake.availability_calls] == [SHOP_B.shop_id]


@pytest.mark.asyncio
async def test_execute_filters_by_address_case_insensitively() -> None:
    fake = FakeBookingGateway([SHOP_A])

    result = await make_handler(fake).execute("ha noi")

    assert result.outcome is HandlerOutcome.SUCCESS
    assert result.data["shops"] == (SHOP_A,)


@pytest.mark.asyncio
async def test_execute_propagates_domain_exception() -> None:
    error = InvalidBookingDataError("Invalid shop search.")
    fake = FakeBookingGateway([], error=error)

    with pytest.raises(InvalidBookingDataError) as exc_info:
        await make_handler(fake).execute("invalid")

    assert exc_info.value is error
    assert fake.search_shops_call_count == 1
