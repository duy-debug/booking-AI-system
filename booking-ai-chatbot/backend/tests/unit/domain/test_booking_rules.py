"""Tests for booking domain rules."""

from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest

from app.domain.booking import (
    Customer,
    Service,
    Shop,
    TherapistPreference,
    TherapistPreferenceType,
)
from app.domain.booking_context import BookingContext
from app.domain.booking_rules import BookingRules
from app.domain.exceptions import (
    BookingContextNotReadyError,
    CustomerNotAllowedError,
    CustomerVerificationRequiredError,
    InvalidBookingDataError,
    InvalidCustomerCountError,
    InvalidDurationError,
    PhoneNotConfirmedError,
    TherapistNotAllowedForGroupError,
)

VIETNAM_TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")
FIXED_NOW = datetime(2026, 8, 1, 10, 0, tzinfo=VIETNAM_TIMEZONE)
SHOP = Shop(
    shop_id=UUID("11111111-1111-1111-1111-111111111111"),
    name="Central Spa",
)
SERVICE = Service(
    service_id=UUID("22222222-2222-2222-2222-222222222222"),
    name="Aromatherapy",
    duration_minutes=60,
    price=Decimal("500000.00"),
)
CUSTOMER = Customer(phone="0901234567", name="Nguyen An")


def make_valid_context() -> BookingContext:
    return BookingContext(
        conversation_id="conversation-1",
        shop=SHOP,
        service=SERVICE,
        customer=CUSTOMER,
        booking_date=date(2099, 1, 1),
        start_time=time(10, 30),
        num_customer=1,
        duration_minutes=60,
        phone=CUSTOMER.phone,
        phone_confirmed=True,
        ng_list_checked=True,
    )


@pytest.mark.parametrize(
    "phone",
    [
        "0901234567",
        "+84901234567",
        "090 123 4567",
        "090-123-4567",
        "+84 90-123-4567",
    ],
)
def test_validate_phone_accepts_valid_formats(phone: str) -> None:
    BookingRules.validate_phone(phone)


@pytest.mark.parametrize(
    "phone",
    [
        "12345678",
        "09012abc67",
        "",
    ],
)
def test_validate_phone_rejects_invalid_values(phone: str) -> None:
    with pytest.raises(InvalidBookingDataError):
        BookingRules.validate_phone(phone)


@pytest.mark.parametrize("duration_minutes", [30, 45, 60, 75, 90, 120])
def test_validate_service_duration_accepts_valid_value(duration_minutes: int) -> None:
    BookingRules.validate_service_duration(duration_minutes)


@pytest.mark.parametrize("duration_minutes", [0, -15, 20, 50])
def test_validate_service_duration_rejects_invalid_values(
    duration_minutes: int,
) -> None:
    with pytest.raises(InvalidDurationError):
        BookingRules.validate_service_duration(duration_minutes)


def test_validate_booking_datetime_accepts_future_datetime() -> None:
    BookingRules.validate_booking_datetime(
        date(2026, 8, 1),
        time(10, 1),
        now=FIXED_NOW,
    )


@pytest.mark.parametrize(
    ("booking_date", "start_time"),
    [
        (date(2026, 8, 1), time(9, 59)),
        (date(2026, 8, 1), time(10, 0)),
    ],
)
def test_validate_booking_datetime_rejects_non_future_datetime(
    booking_date: date,
    start_time: time,
) -> None:
    with pytest.raises(InvalidBookingDataError):
        BookingRules.validate_booking_datetime(
            booking_date,
            start_time,
            now=FIXED_NOW,
        )


def test_validate_booking_datetime_treats_naive_now_as_vietnam_time() -> None:
    BookingRules.validate_booking_datetime(
        date(2026, 8, 1),
        time(10, 1),
        now=datetime(2026, 8, 1, 10, 0),
    )


def test_validate_create_context_accepts_complete_valid_context() -> None:
    BookingRules.validate_create_context(make_valid_context())


@pytest.mark.parametrize(
    "missing_field",
    ["shop", "customer", "booking_date", "start_time"],
)
def test_validate_create_context_rejects_missing_required_data(
    missing_field: str,
) -> None:
    context = make_valid_context()
    setattr(context, missing_field, None)

    with pytest.raises(BookingContextNotReadyError):
        BookingRules.validate_create_context(context)


def test_validate_create_context_requires_main_course() -> None:
    context = make_valid_context()
    context.service = None

    with pytest.raises(BookingContextNotReadyError):
        BookingRules.validate_create_context(context)


@pytest.mark.parametrize("num_customer", [0, -1, 4])
def test_validate_create_context_rejects_customer_count(
    num_customer: int,
) -> None:
    context = make_valid_context()
    context.num_customer = num_customer

    with pytest.raises(InvalidCustomerCountError):
        BookingRules.validate_create_context(context)


def test_validate_create_context_requires_confirmed_phone() -> None:
    context = make_valid_context()
    context.phone_confirmed = False

    with pytest.raises(PhoneNotConfirmedError):
        BookingRules.validate_create_context(context)


def test_validate_create_context_requires_customer_verification() -> None:
    context = make_valid_context()
    context.ng_list_checked = False

    with pytest.raises(CustomerVerificationRequiredError):
        BookingRules.validate_create_context(context)


def test_validate_create_context_rejects_ng_customer() -> None:
    context = make_valid_context()
    context.is_ng_customer = True

    with pytest.raises(CustomerNotAllowedError):
        BookingRules.validate_create_context(context)


def test_validate_create_context_accepts_group_gender_but_rejects_personal() -> None:
    context = make_valid_context()
    context.num_customer = 2
    context.therapist_preference = TherapistPreference(
        TherapistPreferenceType.FEMALE
    )

    BookingRules.validate_create_context(context)

    context.therapist_preference = TherapistPreference(
        TherapistPreferenceType.PERSONAL,
        therapist_name="Mai",
    )

    with pytest.raises(TherapistNotAllowedForGroupError):
        BookingRules.validate_create_context(context)


def test_validate_create_context_does_not_mutate_context() -> None:
    context = make_valid_context()
    original_values = (
        context.conversation_id,
        context.state,
        context.shop,
        context.service,
        context.customer,
        context.booking_date,
        context.start_time,
        context.num_customer,
        context.duration_minutes,
        context.phone,
        context.phone_confirmed,
        context.ng_list_checked,
        context.is_ng_customer,
        context.booking_id,
        context.pending_action,
    )

    BookingRules.validate_create_context(context)

    assert (
        context.conversation_id,
        context.state,
        context.shop,
        context.service,
        context.customer,
        context.booking_date,
        context.start_time,
        context.num_customer,
        context.duration_minutes,
        context.phone,
        context.phone_confirmed,
        context.ng_list_checked,
        context.is_ng_customer,
        context.booking_id,
        context.pending_action,
    ) == original_values
