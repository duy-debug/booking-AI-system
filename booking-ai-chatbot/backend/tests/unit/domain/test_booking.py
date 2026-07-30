"""Tests for core booking domain models."""

from dataclasses import FrozenInstanceError
from datetime import date, time
from decimal import Decimal
from uuid import UUID

import pytest

from app.domain.booking import Booking, Customer, Service, Shop


SHOP_ID = UUID("11111111-1111-1111-1111-111111111111")
SERVICE_ID = UUID("22222222-2222-2222-2222-222222222222")
BOOKING_ID = UUID("33333333-3333-3333-3333-333333333333")


def make_shop() -> Shop:
    return Shop(shop_id=SHOP_ID, name="Central Spa")


def make_service() -> Service:
    return Service(
        service_id=SERVICE_ID,
        name="Aromatherapy",
        duration_minutes=60,
        price=Decimal("500000.00"),
    )


def make_customer() -> Customer:
    return Customer(phone="0901234567", name="Nguyen An")


def make_booking() -> Booking:
    return Booking(
        booking_id=BOOKING_ID,
        status="confirmed",
        shop=make_shop(),
        service=make_service(),
        customer=make_customer(),
        booking_date=date(2026, 8, 1),
        start_time=time(10, 30),
    )


def test_create_shop() -> None:
    shop = make_shop()

    assert shop.shop_id == SHOP_ID
    assert shop.name == "Central Spa"


def test_create_service() -> None:
    service = make_service()

    assert service.service_id == SERVICE_ID
    assert service.duration_minutes == 60
    assert service.price == Decimal("500000.00")


def test_create_customer() -> None:
    customer = make_customer()

    assert customer.phone == "0901234567"
    assert customer.name == "Nguyen An"


def test_booking_contains_domain_objects() -> None:
    booking = make_booking()

    assert booking.booking_id == BOOKING_ID
    assert booking.status == "confirmed"
    assert booking.shop == make_shop()
    assert booking.service == make_service()
    assert booking.customer == make_customer()


@pytest.mark.parametrize(
    "model,field_name,new_value",
    [
        (make_shop(), "name", "Another Shop"),
        (make_service(), "name", "Another Service"),
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
