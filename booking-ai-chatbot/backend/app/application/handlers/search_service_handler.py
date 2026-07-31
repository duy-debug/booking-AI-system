"""Application handler for searching a shop's date-aware service catalog."""

from datetime import date
from uuid import UUID

from app.application.ports.booking_gateway import BookingGateway
from app.domain.booking import Service


class SearchServiceHandler:
    """Coordinates the service search use case for a shop."""

    def __init__(self, booking_gateway: BookingGateway) -> None:
        self._booking_gateway = booking_gateway

    async def execute(
        self,
        shop_id: UUID,
        booking_date: date,
        query: str | None = None,
    ) -> list[Service]:
        """Return services found by the booking gateway for a shop."""
        return await self._booking_gateway.search_services(
            shop_id=shop_id,
            booking_date=booking_date,
            query=query,
        )
