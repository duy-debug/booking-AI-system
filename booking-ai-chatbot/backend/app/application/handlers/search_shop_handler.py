"""Application handler for searching shops."""

from app.application.ports.booking_gateway import BookingGateway
from app.domain.booking import Shop


class SearchShopHandler:
    """Coordinates the shop search use case."""

    def __init__(self, booking_gateway: BookingGateway) -> None:
        self._booking_gateway = booking_gateway

    async def execute(self, query: str | None = None) -> list[Shop]:
        """Return the POS shop catalog, optionally filtered locally."""
        shops = await self._booking_gateway.search_shops()
        normalized_query = query.strip().casefold() if query is not None else ""
        if not normalized_query:
            return shops
        return [
            shop
            for shop in shops
            if normalized_query in shop.name.casefold()
            or (
                shop.address is not None
                and normalized_query in shop.address.casefold()
            )
        ]
