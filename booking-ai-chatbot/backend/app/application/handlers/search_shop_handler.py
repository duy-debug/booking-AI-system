"""Application handler for searching shops."""

from app.application.ports.booking_gateway import BookingGateway
from app.domain.booking import Shop


class SearchShopHandler:
    """Coordinates the shop search use case."""

    def __init__(self, booking_gateway: BookingGateway) -> None:
        self._booking_gateway = booking_gateway

    async def execute(self, query: str | None = None) -> list[Shop]:
        """Return shops found by the booking gateway."""
        return await self._booking_gateway.search_shops(query)
