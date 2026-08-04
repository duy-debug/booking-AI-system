"""Application handler for searching shops."""

import unicodedata

from app.application.ports.booking_gateway import BookingGateway
from app.domain.booking import Shop


class SearchShopHandler:
    """Coordinates the shop search use case."""

    def __init__(self, booking_gateway: BookingGateway) -> None:
        self._booking_gateway = booking_gateway

    async def execute(self, query: str | None = None) -> list[Shop]:
        """Return the POS shop catalog, optionally filtered locally."""
        shops = _unique_named_shops(await self._booking_gateway.search_shops())
        normalized_query = _normalize_search_text(query) if query is not None else ""
        if not normalized_query:
            return shops
        return [
            shop
            for shop in shops
            if normalized_query in _normalize_search_text(shop.name)
            or (
                shop.address is not None
                and normalized_query in _normalize_search_text(shop.address)
            )
        ]


def _normalize_search_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.strip().casefold())
    return "".join(
        character
        for character in decomposed
        if unicodedata.category(character) != "Mn"
    ).replace("đ", "d")


def _unique_named_shops(shops: list[Shop]) -> list[Shop]:
    """Remove only invalid/duplicate names; never infer activity from wording."""
    if not shops:
        return shops
    unique: list[Shop] = []
    seen: set[str] = set()
    for shop in shops:
        key = _normalize_search_text(shop.name)
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(shop)
    return unique
