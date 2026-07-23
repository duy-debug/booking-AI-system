from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# Mô tả giờ mở và đóng cửa của shop trong ngày nghiệp vụ.
class ScheduleBusinessHoursResponse(BaseModel):
    open: str
    close: str
    spans_midnight: bool


# Mô tả phần thời gian timeline mà frontend yêu cầu hiển thị.
class ScheduleViewWindowResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_: str = Field(alias="from")
    to: str
    spans_midnight: bool


# Thông tin shop và cấu hình thời gian cần để frontend dựng timeline.
class ScheduleShopResponse(BaseModel):
    shop_id: UUID
    name: str
    timezone: str
    minimum_booking_advance_minutes: int
    therapist_break_minutes: int
    business_hours: ScheduleBusinessHoursResponse


# Therapist được hiển thị thành một resource row trên timeline.
class ScheduleTherapistResponse(BaseModel):
    therapist_id: UUID
    name: str | None
    gender: str | None
    is_active: bool


# Ca làm việc của therapist trong ngày nghiệp vụ.
class ScheduleShiftResponse(BaseModel):
    shift_id: UUID
    therapist_id: UUID
    therapist_name: str | None
    start_time: str
    end_time: str
    is_active: bool
    spans_midnight: bool


# Khoảng thời gian bị chặn trên timeline của therapist.
class ScheduleBlockedRangeResponse(BaseModel):
    therapist_id: UUID
    therapist_name: str | None
    start_time: str
    end_time: str
    spans_midnight: bool
    reason: str | None


# Snapshot course được gắn với một reservation trên timeline.
class ScheduleCourseResponse(BaseModel):
    course_role: str
    course_name_snapshot: str
    duration_snapshot: int | None
    price_snapshot: float


# Một người trong booking cùng therapist và course được phân công.
class ScheduleReservationResponse(BaseModel):
    reservation_id: UUID
    person_index: int
    therapist_id: UUID
    therapist_name: str | None
    start_time: str
    end_time: str
    status: str
    assignment_source: str
    spans_midnight: bool
    courses: list[ScheduleCourseResponse]


# Thông tin khách hàng rút gọn đi kèm block booking trên timeline.
class ScheduleCustomerResponse(BaseModel):
    customer_id: UUID | None
    phone: str | None
    name: str | None


# Booking đã được tổng hợp để frontend ánh xạ thành các block theo reservation.
class ScheduleBookingResponse(BaseModel):
    booking_id: UUID
    pos_booking_code: str | None
    customer: ScheduleCustomerResponse | None
    booking_date: date
    start_time: str
    end_time: str
    status: str
    number_of_people: int
    total_duration_minutes: int | None
    therapist_request_type: str
    requested_therapist_id: UUID | None
    spans_midnight: bool
    reservations: list[ScheduleReservationResponse]


# Response tổng hợp của một ngày gồm resource, ca làm, vùng chặn và booking.
class ScheduleResponse(BaseModel):
    shop: ScheduleShopResponse
    date: date
    view_window: ScheduleViewWindowResponse
    therapists: list[ScheduleTherapistResponse]
    shifts: list[ScheduleShiftResponse]
    blocked_ranges: list[ScheduleBlockedRangeResponse]
    bookings: list[ScheduleBookingResponse]
    booking_statuses: list[str]
