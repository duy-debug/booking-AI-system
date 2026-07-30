"""Application port for accessing the external booking system."""

from datetime import date, time
from typing import Protocol
from uuid import UUID

from app.domain.booking import Booking, Customer, Service, Shop


class BookingGateway(Protocol):
    """Defines booking operations required by the application layer."""

    async def search_shops(self, query: str | None = None) -> list[Shop]:
        """Return shops matching an optional search query."""
        ...

    async def search_services(
        self,
        shop_id: UUID,
        query: str | None = None,
    ) -> list[Service]:
        """Return services offered by a shop that match an optional query."""
        ...

    async def check_availability(
        self,
        shop_id: UUID,
        service_id: UUID,
        booking_date: date,
    ) -> list[time]:
        """Return displayable available start times for a service and date."""
        ...

    async def create_booking(
        self,
        shop_id: UUID,
        service_id: UUID,
        customer: Customer,
        booking_date: date,
        start_time: time,
    ) -> Booking:
        """Create and return an official booking."""
        ...

    async def lookup_booking(self, booking_id: UUID) -> Booking:
        """Return an official booking by its identifier."""
        ...

    async def reschedule_booking(
        self,
        booking_id: UUID,
        booking_date: date,
        start_time: time,
    ) -> Booking:
        """Reschedule and return the updated official booking."""
        ...

    async def cancel_booking(self, booking_id: UUID) -> Booking:
        """Cancel and return the updated official booking."""
        ...
