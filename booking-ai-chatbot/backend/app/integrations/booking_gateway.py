from __future__ import annotations

from typing import Any

from app.integrations import booking_api


class HttpBookingGateway:
    # Tạo booking qua đúng Public Booking API và truyền idempotency key.
    async def create_booking(self, payload: dict[str, Any], idempotency_key: str) -> dict[str, Any]:
        return await booking_api.create_booking(payload, idempotency_key)

    # Cập nhật hoặc hủy booking qua Public Booking API, không gọi API admin.
    async def update_booking(self, booking_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return await booking_api.update_booking(booking_id, payload)
