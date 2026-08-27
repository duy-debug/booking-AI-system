"""Tests for core booking domain models."""

from dataclasses import FrozenInstanceError
from datetime import date, time
from decimal import Decimal
from uuid import UUID

import pytest

from app.domain.booking_models import (
    Booking,
    BookingOption,
    Course,
    CourseSelection,
    CourseType,
    Customer,
    InvalidBookingDataError,
    InvalidCourseSelectionError,
    InvalidCustomerCountError,
    InvalidDurationError,
    Shop,
    TherapistNotAllowedForGroupError,
    TherapistPreference,
    TherapistPreferenceType,
)

SHOP_ID = UUID("11111111-1111-1111-1111-111111111111")
SERVICE_ID = UUID("22222222-2222-2222-2222-222222222222")
BOOKING_ID = UUID("33333333-3333-3333-3333-333333333333")
ADDON_ID = UUID("44444444-4444-4444-4444-444444444444")


def make_shop() -> Shop:
    return Shop(shop_id=SHOP_ID, name="Central Spa")


def make_service() -> Course:
    return Course(
        course_id=SERVICE_ID,
        name="Aromatherapy",
        duration_minutes=60,
        price=Decimal("500000.00"),
    )


def make_customer() -> Customer:
    return Customer(phone="0901234567", name="Nguyen An")


def make_addon(
    course_id: UUID = ADDON_ID,
    name: str = "Essential oil",
) -> Course:
    return Course(
        course_id=course_id,
        name=name,
        duration_minutes=15,
        price=Decimal("100000.00"),
        course_type=CourseType.ADDON,
    )


def make_booking(
    *,
    num_customer: int = 1,
    duration_minutes: int = 60,
    therapist_preference: TherapistPreference | None = None,
    addons: tuple[Course, ...] = (),
    reservation_code: str | None = None,
) -> Booking:
    return Booking(
        booking_id=BOOKING_ID,
        status="confirmed",
        shop=make_shop(),
        main_course=make_service(),
        customer=make_customer(),
        booking_date=date(2026, 8, 1),
        start_time=time(10, 30),
        num_customer=num_customer,
        duration_minutes=duration_minutes,
        therapist_preference=therapist_preference,
        addons=addons,
        reservation_code=reservation_code,
    )


def test_create_shop() -> None:
    shop = make_shop()

    assert shop.shop_id == SHOP_ID
    assert shop.name == "Central Spa"


def test_create_service() -> None:
    service = make_service()

    assert service.course_id == SERVICE_ID
    assert service.duration_minutes == 60
    assert service.price == Decimal("500000.00")
    assert service.course_type is CourseType.MAIN


@pytest.mark.parametrize("duration_minutes", [0, -15, 20, 50])
def test_service_rejects_invalid_duration(duration_minutes: int) -> None:
    with pytest.raises(InvalidDurationError):
        Course(
            course_id=SERVICE_ID,
            name="Invalid service",
            duration_minutes=duration_minutes,
            price=Decimal("500000.00"),
        )


def test_addon_allows_positive_duration_outside_slot_grid() -> None:
    addon = Course(
        course_id=ADDON_ID,
        name="Foot acupressure",
        duration_minutes=20,
        price=Decimal("100000.00"),
        course_type=CourseType.ADDON,
    )

    assert addon.duration_minutes == 20
    assert addon.course_type is CourseType.ADDON


def test_create_customer() -> None:
    customer = make_customer()

    assert customer.phone == "0901234567"
    assert customer.name == "Nguyen An"


def test_booking_contains_domain_objects() -> None:
    booking = make_booking()

    assert booking.booking_id == BOOKING_ID
    assert booking.status == "confirmed"
    assert booking.shop == make_shop()
    assert booking.main_course == make_service()
    assert booking.customer == make_customer()
    assert booking.num_customer == 1
    assert booking.duration_minutes == 60
    assert booking.options == ()


@pytest.mark.parametrize(
    "model,field_name,new_value",
    [
        (make_shop(), "name", "Another Shop"),
        (make_service(), "name", "Another Course"),
        (make_customer(), "phone", "0900000000"),
        (make_booking(), "status", "cancelled"),
    ],
)
def test_domain_models_are_immutable(
    model: object,
    field_name: str,
    new_value: object,
) -> None:
    with pytest.raises(FrozenInstanceError):
        setattr(model, field_name, new_value)


@pytest.mark.parametrize(
    "left,right",
    [
        (make_shop(), make_shop()),
        (make_service(), make_service()),
        (make_customer(), make_customer()),
        (make_booking(), make_booking()),
    ],
)
def test_models_with_same_data_are_equal(left: object, right: object) -> None:
    assert left == right


@pytest.mark.parametrize("model", [make_shop(), make_service(), make_customer(), make_booking()])
def test_slots_prevent_adding_undeclared_attributes(model: object) -> None:
    assert not hasattr(model, "__dict__")

    with pytest.raises((AttributeError, TypeError)):
        object.__setattr__(model, "unexpected", "value")


def test_optional_fields_default_to_none() -> None:
    shop = make_shop()
    customer = Customer(phone="0901234567")

    assert shop.address is None
    assert shop.phone is None
    assert customer.name is None


@pytest.mark.parametrize("num_customer", [0, -1, 4])
def test_booking_rejects_invalid_customer_count(num_customer: int) -> None:
    with pytest.raises(InvalidCustomerCountError):
        Booking(
            booking_id=BOOKING_ID,
            status="confirmed",
            shop=make_shop(),
            main_course=make_service(),
            customer=make_customer(),
            booking_date=date(2026, 8, 1),
            start_time=time(10, 30),
            num_customer=num_customer,
        )


@pytest.mark.parametrize("duration", [0, -15, 20, 50])
def test_booking_rejects_invalid_duration(duration: int) -> None:
    with pytest.raises(InvalidDurationError):
        Booking(
            booking_id=BOOKING_ID,
            status="confirmed",
            shop=make_shop(),
            main_course=make_service(),
            customer=make_customer(),
            booking_date=date(2026, 8, 1),
            start_time=time(10, 30),
            duration_minutes=duration,
        )


def test_personal_therapist_requires_identifier_or_name() -> None:
    with pytest.raises(InvalidBookingDataError):
        TherapistPreference(TherapistPreferenceType.PERSONAL)


@pytest.mark.parametrize(
    "preference",
    [
        TherapistPreference(TherapistPreferenceType.NONE),
        TherapistPreference(TherapistPreferenceType.MALE),
        TherapistPreference(TherapistPreferenceType.FEMALE),
        TherapistPreference(
            TherapistPreferenceType.PERSONAL,
            therapist_name="Mai",
        ),
    ],
)
def test_valid_therapist_preferences(preference: TherapistPreference) -> None:
    assert isinstance(preference, TherapistPreference)


def test_booking_rejects_duplicate_option_ids() -> None:
    options = (
        BookingOption(option_id="oil", name="Essential oil"),
        BookingOption(option_id="oil", name="Another oil"),
    )

    with pytest.raises(InvalidBookingDataError):
        Booking(
            booking_id=BOOKING_ID,
            status="confirmed",
            shop=make_shop(),
            main_course=make_service(),
            customer=make_customer(),
            booking_date=date(2026, 8, 1),
            start_time=time(10, 30),
            options=options,
        )


def test_booking_options_are_stored_as_immutable_tuple() -> None:
    option = BookingOption(option_id="oil", name="Essential oil")
    booking = Booking(
        booking_id=BOOKING_ID,
        status="confirmed",
        shop=make_shop(),
        main_course=make_service(),
        customer=make_customer(),
        booking_date=date(2026, 8, 1),
        start_time=time(10, 30),
        options=(option,),
    )

    assert booking.options == (option,)
    assert isinstance(booking.options, tuple)


@pytest.mark.parametrize("num_customer", [1, 2, 3])
def test_booking_accepts_supported_customer_counts(num_customer: int) -> None:
    booking = make_booking(num_customer=num_customer)

    assert booking.num_customer == num_customer


@pytest.mark.parametrize("duration_minutes", [30, 45, 60, 75, 90, 120])
def test_booking_accepts_supported_durations(duration_minutes: int) -> None:
    booking = make_booking(duration_minutes=duration_minutes)

    assert booking.duration_minutes == duration_minutes


def test_course_selection_accepts_one_main_course() -> None:
    selection = CourseSelection(main_course=make_service())

    assert selection.main_course == make_service()
    assert selection.addons == ()


def test_course_selection_accepts_one_or_many_addons() -> None:
    first = make_addon()
    second = make_addon(
        UUID("55555555-5555-5555-5555-555555555555"),
        "Hot stone",
    )

    selection = CourseSelection(main_course=make_service(), addons=(first, second))

    assert selection.addons == (first, second)


def test_course_selection_rejects_addon_as_main_course() -> None:
    with pytest.raises(InvalidCourseSelectionError):
        CourseSelection(main_course=make_addon())


def test_course_selection_rejects_main_course_in_addons() -> None:
    with pytest.raises(InvalidCourseSelectionError):
        CourseSelection(main_course=make_service(), addons=(make_service(),))


def test_course_selection_rejects_duplicate_addons() -> None:
    addon = make_addon()

    with pytest.raises(InvalidCourseSelectionError):
        CourseSelection(main_course=make_service(), addons=(addon, addon))


def test_course_selection_rejects_main_course_repeated_as_addon() -> None:
    repeated = Course(
        course_id=SERVICE_ID,
        name="Invalid duplicate",
        duration_minutes=15,
        price=Decimal("100000.00"),
        course_type=CourseType.ADDON,
    )

    with pytest.raises(InvalidCourseSelectionError):
        CourseSelection(main_course=make_service(), addons=(repeated,))


def test_single_booking_accepts_personal_therapist() -> None:
    preference = TherapistPreference(
        TherapistPreferenceType.PERSONAL,
        therapist_name="Mai",
    )

    booking = make_booking(therapist_preference=preference)

    assert booking.therapist_preference is preference


@pytest.mark.parametrize(
    ("num_customer", "preference_type"),
    [
        (2, TherapistPreferenceType.PERSONAL),
    ],
)
def test_group_booking_rejects_therapist_preference(
    num_customer: int,
    preference_type: TherapistPreferenceType,
) -> None:
    preference = TherapistPreference(
        preference_type,
        therapist_name="Mai" if preference_type is TherapistPreferenceType.PERSONAL else None,
    )

    with pytest.raises(TherapistNotAllowedForGroupError):
        make_booking(
            num_customer=num_customer,
            therapist_preference=preference,
        )


def test_booking_accepts_none_preference_for_group() -> None:
    preference = TherapistPreference(TherapistPreferenceType.NONE)

    booking = make_booking(num_customer=2, therapist_preference=preference)

    assert booking.therapist_preference is preference


def test_booking_accepts_gender_preference_for_group() -> None:
    preference = TherapistPreference(TherapistPreferenceType.FEMALE)

    booking = make_booking(num_customer=3, therapist_preference=preference)

    assert booking.therapist_preference is preference


def test_booking_exposes_course_selection_and_optional_reservation_code() -> None:
    addon = make_addon()
    booking = make_booking(addons=(addon,), reservation_code="RSV-001")

    assert booking.course_selection == CourseSelection(make_service(), (addon,))
    assert booking.reservation_code == "RSV-001"
