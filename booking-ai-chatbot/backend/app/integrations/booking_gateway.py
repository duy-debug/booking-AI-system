from __future__ import annotations

from typing import Any

from app.integrations import booking_api


class HttpBookingGateway:
    # Tra cứu booking bằng contract công khai có đối chiếu số điện thoại chủ booking.
    async def lookup_booking(self, booking_id: str, phone: str) -> dict[str, Any]:
        return await booking_api.lookup_booking(booking_id, phone)

    # Tạo booking qua đúng Public Booking API và truyền idempotency key.
    async def create_booking(self, payload: dict[str, Any], idempotency_key: str) -> dict[str, Any]:
        return await booking_api.create_booking(payload, idempotency_key)

    # Cập nhật hoặc hủy booking qua Public Booking API, không gọi API admin.
    async def update_booking(self, booking_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return await booking_api.update_booking(booking_id, payload)

    async def is_reschedule_available(
        self,
        booking: dict[str, Any],
        booking_date: str,
        start_time: str,
    ) -> bool:
        reservations = booking.get("reservations") or []
        courses = reservations[0].get("courses", []) if reservations else []
        main = next(
            (item for item in courses if item.get("course_role") == "main"),
            None,
        )
        if main is None:
            return False
        addon_ids = [
            str(item["course_id"])
            for item in courses
            if item.get("course_role") == "addon"
        ]
        result = await booking_api.get_available_slots(
            shop_id=str(booking["shop_id"]),
            booking_date=booking_date,
            number_of_people=int(booking["number_of_people"]),
            main_course_id=str(main["course_id"]),
            start_time=start_time,
            addon_course_ids=",".join(addon_ids) or None,
        )
        slots = result.get("data", []) if isinstance(result, dict) else []
        return any(
            str(slot.get("start_time", ""))[:5] == start_time for slot in slots
        )
