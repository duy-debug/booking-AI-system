from __future__ import annotations

from typing import Any
from uuid import uuid4

import httpx

from app.core.config import settings
from app.core.exceptions import AppError

_client: httpx.AsyncClient | None = None


# Khởi tạo HTTP client dùng lại connection pool cho mọi lời gọi Booking Backend.
async def init_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            base_url=settings.BOOKING_API_URL.rstrip("/"),
            timeout=settings.BOOKING_API_TIMEOUT_SECONDS,
        )
    return _client


# Lấy HTTP client đã khởi tạo và tự khởi tạo khi được gọi độc lập.
async def get_client() -> httpx.AsyncClient:
    return await init_client()


# Đóng connection pool khi FastAPI dừng để không rò rỉ socket.
async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


# Chuẩn hóa lỗi mạng và RFC 9457 từ Booking Backend thành AppError thống nhất.
async def _request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    unwrap_data: bool = True,
) -> Any:
    client = await get_client()
    request_headers = {"X-Correlation-ID": str(uuid4())}
    if settings.BOOKING_API_SERVICE_KEY:
        request_headers["X-Service-Key"] = settings.BOOKING_API_SERVICE_KEY
    if headers:
        request_headers.update(headers)
    try:
        response = await client.request(
            method, path, params=params, json=json, headers=request_headers
        )
    except httpx.TimeoutException as exc:
        raise AppError(
            503,
            code="BOOKING_API_TIMEOUT",
            detail="Booking Backend phản hồi quá thời gian cho phép.",
        ) from exc
    except httpx.RequestError as exc:
        raise AppError(
            502,
            code="BOOKING_API_UNAVAILABLE",
            detail="Không thể kết nối đến Booking Backend.",
        ) from exc

    if response.status_code >= 400:
        try:
            body = response.json()
        except ValueError:
            body = {}
        nested = body.get("detail") if isinstance(body, dict) else None
        problem = nested if isinstance(nested, dict) else body
        code = problem.get("code", "BOOKING_API_ERROR")
        detail = problem.get("detail") or (
            nested if isinstance(nested, str) else "Booking Backend trả về lỗi."
        )
        raise AppError(response.status_code, code=code, detail=str(detail))

    if response.status_code == 204:
        return None
    body = response.json()
    if unwrap_data and isinstance(body, dict):
        return body.get("data", body)
    return body


# Lấy danh sách cửa hàng đang hoạt động từ public API.
async def list_shops() -> list[dict[str, Any]]:
    result = await _request("GET", "/api/shops", params={"is_active": "true"})
    return result if isinstance(result, list) else []


# Lấy chi tiết một cửa hàng công khai.
async def get_shop(shop_id: str) -> dict[str, Any]:
    return await _request("GET", f"/api/shops/{shop_id}")


# Lấy danh sách course công khai thuộc cửa hàng.
async def list_courses(shop_id: str, course_type: str | None = None) -> list[dict[str, Any]]:
    params = {"course_type": course_type} if course_type else None
    result = await _request("GET", f"/api/shops/{shop_id}/courses", params=params)
    return result if isinstance(result, list) else []


# Tra cứu slot theo đúng các query parameter mà Booking Backend công bố.
async def get_available_slots(
    *,
    shop_id: str,
    booking_date: str,
    number_of_people: int,
    main_course_id: str,
    start_time: str | None = None,
    addon_course_ids: str | None = None,
    therapist_request_type: str | None = None,
    therapist_id: str | None = None,
    therapist_gender: str | None = None,
) -> dict[str, Any]:
    params = {
        "booking_date": booking_date,
        "number_of_people": number_of_people,
        "main_course_id": main_course_id,
        "start_time": start_time,
        "addon_course_ids": addon_course_ids,
        "therapist_request_type": therapist_request_type,
        "therapist_id": therapist_id,
        "therapist_gender": therapist_gender,
    }
    return await _request(
        "GET",
        f"/api/shops/{shop_id}/available-slots",
        params={key: value for key, value in params.items() if value is not None},
        unwrap_data=False,
    )


# Lấy therapist còn trống trong một khung giờ để booking một người có thể chỉ định.
async def get_available_therapists(
    *,
    shop_id: str,
    booking_date: str,
    start_time: str,
    end_time: str,
    gender: str | None = None,
) -> list[dict[str, Any]]:
    params = {
        "booking_date": booking_date,
        "start_time": start_time,
        "end_time": end_time,
        "gender": gender,
    }
    result = await _request(
        "GET",
        f"/api/shops/{shop_id}/available-therapists",
        params={key: value for key, value in params.items() if value is not None},
    )
    return result if isinstance(result, list) else []


# Kiểm tra NG list và giới hạn đặt lịch trước khi tạo pending action.
async def check_eligibility(phone: str, shop_id: str) -> dict[str, Any]:
    return await _request(
        "POST",
        "/api/booking-eligibility-checks",
        json={"phone": phone, "shop_id": shop_id},
    )


# Tạo booking với idempotency key để retry không tạo bản ghi trùng.
async def create_booking(
    payload: dict[str, Any], idempotency_key: str | None = None
) -> dict[str, Any]:
    key = idempotency_key or str(payload.pop("_idempotency_key", uuid4()))
    return await _request(
        "POST",
        "/api/bookings",
        json=payload,
        headers={"Idempotency-Key": key},
    )


# Lấy chi tiết booking từ public API.
async def get_booking(booking_id: str) -> dict[str, Any]:
    return await _request("GET", f"/api/bookings/{booking_id}")


# Tra cứu booking bằng các bộ lọc công khai.
async def list_bookings(**filters: Any) -> list[dict[str, Any]]:
    result = await _request(
        "GET",
        "/api/bookings",
        params={key: value for key, value in filters.items() if value is not None},
    )
    return result if isinstance(result, list) else []


# Cập nhật thông tin booking sau khi application đã xác nhận với khách hàng.
async def update_booking(booking_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return await _request("PATCH", f"/api/bookings/{booking_id}", json=payload)


# Hủy booking bằng PATCH public API thay vì gọi endpoint quản trị.
async def cancel_booking(booking_id: str, reason: str | None = None) -> dict[str, Any]:
    return await update_booking(booking_id, {"status": "cancelled", "cancel_reason": reason})
