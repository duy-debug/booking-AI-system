from datetime import time
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.time_ranges import expand_time_window
from app.schemas.shop import ShopUpdate
from app.services.therapist_availability_service import (
    AvailabilityDayContext,
    TherapistAvailabilityService,
)


# Tạo context tối thiểu cho một therapist có ca và một booking kết thúc lúc 16:00.
def _context(break_minutes: int) -> tuple[AvailabilityDayContext, object]:
    therapist_id = uuid4()
    therapist = SimpleNamespace(
        therapist_id=therapist_id,
        shop_id=uuid4(),
        is_active=True,
        gender="female",
    )
    return (
        AvailabilityDayContext(
            active_shifts=[],
            therapists={therapist_id: therapist},
            shifts_by_therapist={therapist_id: [(time(8), time(22))]},
            blocked_by_therapist={},
            reservations_by_therapist={
                therapist_id: [(time(15), time(16))]
            },
            break_minutes=break_minutes,
        ),
        therapist,
    )


# Xác nhận mốc 16:04 còn thuộc thời gian nghỉ nhưng đúng 16:05 đã khả dụng.
def test_five_minute_break_blocks_until_exact_boundary():
    context, _ = _context(5)

    blocked = TherapistAvailabilityService._evaluate_context(
        context,
        start_time=time(16, 4),
        end_time=time(17),
        request_type="none",
        requested_therapist_id=None,
        requested_gender=None,
    )
    allowed = TherapistAvailabilityService._evaluate_context(
        context,
        start_time=time(16, 5),
        end_time=time(17),
        request_type="none",
        requested_therapist_id=None,
        requested_gender=None,
    )

    assert blocked.available_therapist_count == 0
    assert allowed.available_therapist_count == 1


# Xác nhận booking trước phải kết thúc chậm nhất lúc 14:55 nếu booking hiện tại bắt đầu lúc 15:00.
def test_five_minute_break_also_blocks_before_existing_booking():
    context, _ = _context(5)

    blocked = TherapistAvailabilityService._evaluate_context(
        context,
        start_time=time(14),
        end_time=time(14, 56),
        request_type="none",
        requested_therapist_id=None,
        requested_gender=None,
    )
    allowed = TherapistAvailabilityService._evaluate_context(
        context,
        start_time=time(14),
        end_time=time(14, 55),
        request_type="none",
        requested_therapist_id=None,
        requested_gender=None,
    )

    assert blocked.available_therapist_count == 0
    assert allowed.available_therapist_count == 1


# Xác nhận cấu hình 0 phút giữ hành vi cho phép hai booking chạm biên.
def test_zero_break_allows_touching_booking_boundary():
    context, _ = _context(0)

    result = TherapistAvailabilityService._evaluate_context(
        context,
        start_time=time(16),
        end_time=time(17),
        request_type="none",
        requested_therapist_id=None,
        requested_gender=None,
    )

    assert result.available_therapist_count == 1


# Kiểm tra helper mở rộng đúng hai phía để chặn cả booking trước và booking sau.
def test_break_expands_candidate_window_symmetrically():
    assert expand_time_window(time(16, 5), time(17), 5) == (
        time(16),
        time(17, 5),
    )


# Chỉ bốn giá trị đã thống nhất mới được phép đi qua Pydantic request schema.
@pytest.mark.parametrize("minutes", [0, 5, 10, 15])
def test_shop_accepts_supported_break_values(minutes):
    assert ShopUpdate(therapist_break_minutes=minutes).therapist_break_minutes == minutes


# Mọi giá trị ngoài danh sách đều bị từ chối trước khi truy cập database.
def test_shop_rejects_unsupported_break_value():
    with pytest.raises(ValidationError):
        ShopUpdate(therapist_break_minutes=7)
