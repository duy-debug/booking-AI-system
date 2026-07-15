# Real POS Client — gọi POS API thật qua HTTP
# Dùng httpx để gọi REST API của POS system

from datetime import date, time

import httpx

from app.integrations.pos.base import (
    POSAvailabilityResult,
    POSBookingData,
    POSBookingResult,
    POSSlotData,
    AbstractPOSClient,
)


class RealPOSClient(AbstractPOSClient):
    # Kết nối POS thật qua REST API

    def __init__(self, base_url: str | None, api_key: str | None):
        if not base_url:
            raise ValueError("POS_BASE_URL chưa được cấu hình")
        self._base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = httpx.Client(base_url=self._base_url, headers=self._headers, timeout=10)

    def _build_url(self, path: str) -> str:
        return f"{self._base_url}{path}"

    def check_availability(
        self,
        pos_shop_code: str,
        booking_date: date,
        start_time: time,
        end_time: time,
        number_of_people: int,
    ) -> POSAvailabilityResult:
        # Gọi POS check availability
        try:
            resp = self._client.post(
                "/availability/check",
                json={
                    "shop_code": pos_shop_code,
                    "date": booking_date.isoformat(),
                    "start_time": start_time.isoformat(),
                    "end_time": end_time.isoformat(),
                    "pax": number_of_people,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return POSAvailabilityResult(
                available=data.get("available", False),
                slot_start_time=start_time,
                error_code=None,
            )
        except httpx.HTTPStatusError as e:
            return POSAvailabilityResult(
                available=False,
                slot_start_time=None,
                error_code="POS_TEMPORARY_ERROR",
            )
        except httpx.RequestError as e:
            return POSAvailabilityResult(
                available=False,
                slot_start_time=None,
                error_code="POS_TEMPORARY_ERROR",
            )

    def get_available_slots(
        self,
        pos_shop_code: str,
        booking_date: date,
        total_duration_minutes: int,
        number_of_people: int,
    ) -> list[POSSlotData]:
        # Gọi POS lấy danh sách slot
        try:
            resp = self._client.get(
                "/availability/slots",
                params={
                    "shop_code": pos_shop_code,
                    "date": booking_date.isoformat(),
                    "duration": total_duration_minutes,
                    "pax": number_of_people,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return [
                POSSlotData(
                    start_time=time.fromisoformat(s["start_time"]),
                    end_time=time.fromisoformat(s["end_time"]),
                    available=s.get("available", True),
                )
                for s in data.get("slots", [])
            ]
        except (httpx.HTTPStatusError, httpx.RequestError):
            return []

    def create_booking(self, data: POSBookingData) -> POSBookingResult:
        # Gọi POS tạo booking
        try:
            resp = self._client.post(
                "/bookings",
                json={
                    "shop_code": data.pos_shop_code,
                    "date": data.booking_date.isoformat(),
                    "start_time": data.start_time.isoformat(),
                    "end_time": data.end_time.isoformat(),
                    "pax": data.number_of_people,
                    "customer_phone": data.customer_phone,
                    "customer_name": data.customer_name,
                    "services": [
                        {
                            "code": c["pos_course_code"],
                            "role": c["course_role"],
                            "duration": c["duration"],
                            "price": str(c["price"]),
                        }
                        for c in data.courses
                    ],
                    "therapist_ids": [str(t) for t in data.therapist_ids] if data.therapist_ids else [],
                },
            )
            resp.raise_for_status()
            result = resp.json()
            return POSBookingResult(
                success=True,
                pos_booking_code=result.get("booking_code"),
                error_code=None,
                error_detail=None,
            )
        except httpx.HTTPStatusError as e:
            body = e.response.json() if e.response.content else {}
            return POSBookingResult(
                success=False,
                pos_booking_code=None,
                error_code=body.get("code", "POS_TEMPORARY_ERROR"),
                error_detail=body.get("detail", str(e)),
            )
        except httpx.RequestError as e:
            return POSBookingResult(
                success=False,
                pos_booking_code=None,
                error_code="POS_TEMPORARY_ERROR",
                error_detail=str(e),
            )

    def cancel_booking(self, pos_booking_code: str, reason: str | None = None) -> bool:
        # Gọi POS hủy booking
        try:
            resp = self._client.post(
                f"/bookings/{pos_booking_code}/cancel",
                json={"reason": reason} if reason else {},
            )
            resp.raise_for_status()
            return True
        except (httpx.HTTPStatusError, httpx.RequestError):
            return False

    def lookup_customer(self, phone: str) -> dict | None:
        # Gọi POS tra cứu khách hàng
        try:
            resp = self._client.get("/customers", params={"phone": phone})
            resp.raise_for_status()
            data = resp.json()
            return data.get("customer")
        except (httpx.HTTPStatusError, httpx.RequestError):
            return None
