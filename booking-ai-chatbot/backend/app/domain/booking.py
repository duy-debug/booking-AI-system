"""Core data models for the booking domain."""

from dataclasses import dataclass
from datetime import date, time
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True, slots=True)
class Shop:
    """Represents a shop available for booking."""

    shop_id: UUID
    name: str
    address: str | None = None
    phone: str | None = None


@dataclass(frozen=True, slots=True)
class Service:
    """Represents a service offered by a shop."""

    service_id: UUID
    name: str
    duration_minutes: int
    price: Decimal


@dataclass(frozen=True, slots=True)
class Customer:
    """Represents the customer who makes a booking."""

    phone: str
    name: str | None = None


@dataclass(frozen=True, slots=True)
class Booking:
    """Represents a confirmed booking and its domain data."""

    booking_id: UUID
    status: str
    shop: Shop
    service: Service
    customer: Customer
    booking_date: date
    start_time: time
