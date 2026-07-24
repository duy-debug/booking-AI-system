from __future__ import annotations

from typing import Any

from app.integrations import booking_api
from app.policies.tool_policy import ensure_public_tool


# Lấy danh sách shop qua read-only tool đã nằm trong allowlist.
async def list_shops() -> list[dict[str, Any]]:
    ensure_public_tool("list_shops")
    return await booking_api.list_shops()


# Lấy chi tiết shop để xác minh ID do frontend gửi lên thuộc dữ liệu công khai thật.
async def get_shop(shop_id: str) -> dict[str, Any]:
    ensure_public_tool("get_shop")
    return await booking_api.get_shop(shop_id)


# Lấy danh sách course của shop qua Public Booking API.
async def list_courses(shop_id: str, course_type: str | None = None) -> list[dict[str, Any]]:
    ensure_public_tool("list_courses")
    return await booking_api.list_courses(shop_id, course_type)


# Kiểm tra availability; kết quả chỉ mang tính pre-check trước mutation.
async def get_available_slots(**query: Any) -> dict[str, Any]:
    ensure_public_tool("get_available_slots")
    return await booking_api.get_available_slots(**query)


# Lấy therapist khả dụng cho booking một người sau khi đã xác định thời gian kết thúc.
async def get_available_therapists(**query: Any) -> list[dict[str, Any]]:
    ensure_public_tool("get_available_therapists")
    return await booking_api.get_available_therapists(**query)


# Kiểm tra eligibility trước khi tạo confirmation cho booking.
async def check_eligibility(phone: str, shop_id: str) -> dict[str, Any]:
    ensure_public_tool("check_eligibility")
    return await booking_api.check_eligibility(phone=phone, shop_id=shop_id)


# Lấy booking công khai sau khi tầng workflow đã xác thực khách hàng.
async def get_booking(booking_id: str) -> dict[str, Any]:
    ensure_public_tool("get_booking")
    return await booking_api.get_booking(booking_id)
