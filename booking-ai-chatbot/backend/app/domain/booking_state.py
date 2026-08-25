"""Khai báo các trạng thái của luồng hội thoại đặt lịch."""

from enum import StrEnum


class BookingState(StrEnum):
    """Biểu diễn các trạng thái chính của draft booking trong chatbot."""

    IDLE = "idle"  # Chưa có draft booking đang xử lý hoặc vừa reset conversation.
    COLLECTING_CANCEL_BOOKING_IDENTITY = (
        "collecting_cancel_booking_identity"
    )  # Đang chờ mã booking và số điện thoại để tra cứu lịch cần hủy.
    AWAITING_CANCEL_CONFIRMATION = (
        "awaiting_cancel_confirmation"
    )  # Đã tìm thấy booking và đang chờ khách xác nhận hủy.
    SELECTING_SHOP = "selecting_shop"  # Đang chờ người dùng chọn cửa hàng.
    SELECTING_DATE = "selecting_date"  # Đang chờ chọn ngày đặt lịch.
    SELECTING_PEOPLE = "selecting_people"  # Đang chờ số người.
    SELECTING_DURATION = "selecting_duration"  # Đang chờ thời lượng mong muốn.
    SELECTING_SERVICE = "selecting_service"  # Đang chờ chọn liệu trình chính/add-on.
    SELECTING_TIME = "selecting_time"  # Đang chờ chọn giờ bắt đầu.
    SELECTING_THERAPIST = "selecting_therapist"  # Đang chờ chọn ưu tiên kỹ thuật viên.
    COLLECTING_PHONE = "collecting_phone"  # Đang chờ số điện thoại khách hàng.
    COLLECTING_NAME = "collecting_name"  # Đang chờ tên khách hàng.
    VERIFYING_PHONE = "verifying_phone"  # Đang kiểm tra/xác nhận thông tin số điện thoại.
    AWAITING_CONFIRMATION = "awaiting_confirmation"  # Đã đủ dữ liệu draft và chờ xác nhận cuối.
    BOOKING_EXECUTING = "booking_executing"  # Đang gọi POS để tạo booking thật.
    COMPLETED = "completed"  # Booking đã tạo thành công và luồng hiện tại đã hoàn tất.
    BOOKING_FAILED = "booking_failed"  # Tạo booking thất bại nhưng còn khả năng recovery/retry.
    CANCELLED = "cancelled"  # Người dùng đã hủy luồng draft hiện tại.
