# Mock POS Client — dùng cho development / testing
# Giả lập POS system: tạo mã booking giả, luôn trả available

import uuid
from datetime import date, time, timedelta

from app.integrations.pos.base import (
    POSAvailabilityResult,
    POSBookingData,
    POSBookingResult,
    POSSlotData,
    AbstractPOSClient,
)


class MockPOSClient(AbstractPOSClient):
    # POS mock — không gọi API thật, dùng logic nội bộ

    def __init__(self):
        # Lưu booking code đã tạo — để verify cancel / lookup
        self._created_codes: dict[str, dict] = {}

    def check_availability(
        self,
        pos_shop_code: str,
        booking_date: date,
        start_time: time,
        end_time: time,
        number_of_people: int,
    ) -> POSAvailabilityResult:
        # Mock: luôn available
        return POSAvailabilityResult(
            available=True,
            slot_start_time=start_time,
            error_code=None,
        )

    def get_available_slots(
        self,
        pos_shop_code: str,
        booking_date: date,
        total_duration_minutes: int,
        number_of_people: int,
    ) -> list[POSSlotData]:
        # Mock: trả về 2 slot giả — 10:00 và 14:00
        slots = []
        for hour in [10, 14]:
            st = time(hour, 0)
            et_minutes = hour * 60 + total_duration_minutes
            et = time(et_minutes // 60, et_minutes % 60)
            slots.append(POSSlotData(start_time=st, end_time=et, available=True))
        return slots

    def create_booking(self, data: POSBookingData) -> POSBookingResult:
        # Mock: tạo mã booking giả — unique mỗi lần gọi
        unique_id = uuid.uuid4().hex[:8].upper()
        today_str = date.today().strftime("%Y%m%d")
        pos_code = f"POS-{today_str}-{unique_id}"

        self._created_codes[pos_code] = {
            "pos_shop_code": data.pos_shop_code,
            "booking_date": data.booking_date,
            "start_time": data.start_time,
            "end_time": data.end_time,
        }

        return POSBookingResult(
            success=True,
            pos_booking_code=pos_code,
            error_code=None,
            error_detail=None,
        )

    def cancel_booking(self, pos_booking_code: str, reason: str | None = None) -> bool:
        # Mock: luôn thành công (nếu code tồn tại)
        if pos_booking_code in self._created_codes:
            self._created_codes[pos_booking_code]["cancelled"] = True
            return True
        return False

    def lookup_customer(self, phone: str) -> dict | None:
        # Mock: trả về dữ liệu giả
        return {
            "phone": phone,
            "name": "Test Customer",
            "is_member": True,
            "member_rank": "silver",
            "visit_count": 5,
        }
