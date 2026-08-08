"""Application handler for searching shops."""

import unicodedata

from app.domain.booking_models import BookingGateway, Shop
from app.domain.outcomes import HandlerOutcome, HandlerResult


class SearchShopHandler:
    """Coordinates the shop search use case."""

    # Nhận gateway POS để tải danh sách shop authoritative.
    def __init__(self, booking_gateway: BookingGateway) -> None:
        self._booking_gateway = booking_gateway

    # Tìm cửa hàng theo tên/khu vực sau khi đã lấy catalog từ POS.
    async def execute(self, query: str | None = None) -> HandlerResult:
        """Return the POS shop catalog through the common handler contract."""
        shops = _unique_named_shops(await self._booking_gateway.search_shops())
        normalized_query = _normalize_search_text(query) if query is not None else ""
        if not normalized_query:
            return HandlerResult(HandlerOutcome.SUCCESS, {"shops": tuple(shops)})
        matched = [
            shop
            for shop in shops
            if normalized_query in _normalize_search_text(shop.name)
            or (
                shop.address is not None
                and normalized_query in _normalize_search_text(shop.address)
            )
        ]
        if not matched:
            return HandlerResult(HandlerOutcome.NOT_FOUND, error_code="shop_not_found")
        return HandlerResult(HandlerOutcome.SUCCESS, {"shops": tuple(matched)})


# Chuẩn hóa text tiếng Việt để matching shop không phụ thuộc dấu/case.
def _normalize_search_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.strip().casefold())
    return "".join(
        character for character in decomposed if unicodedata.category(character) != "Mn"
    ).replace("đ", "d")


# Loại shop trùng tên hoặc rỗng để danh sách gợi ý không gây nhiễu cho người dùng.
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
