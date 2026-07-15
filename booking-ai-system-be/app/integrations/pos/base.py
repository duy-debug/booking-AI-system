# Abstract POS Client — interface cho tất cả POS implementation
# Các method này được gọi trong booking flow để đồng bộ với POS

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, time
from uuid import UUID


@dataclass
class POSBookingData:
    # Dữ liệu cần gửi lên POS khi tạo booking
    pos_shop_code: str
    booking_date: date
    start_time: time
    end_time: time
    number_of_people: int
    total_duration_minutes: int
    customer_phone: str
    customer_name: str | None
    courses: list[dict]  # [{pos_course_code, course_role, duration, price}]
    therapist_ids: list[UUID] | None  # ID therapist được gán


@dataclass
class POSBookingResult:
    # Kết quả từ POS sau khi tạo booking
    success: bool
    pos_booking_code: str | None  # Mã booking bên POS
    error_code: str | None  # POS_CONFLICT, POS_TEMPORARY_ERROR, v.v.
    error_detail: str | None


@dataclass
class POSAvailabilityResult:
    # Kết quả kiểm tra availability từ POS
    available: bool
    slot_start_time: time | None  # Slot khả dụng gần nhất
    error_code: str | None


@dataclass
class POSSlotData:
    # Một slot từ POS
    start_time: time
    end_time: time
    available: bool


class AbstractPOSClient(ABC):
    # Abstract class đóng gói giao tiếp với POS system

    @abstractmethod
    def check_availability(
        self,
        pos_shop_code: str,
        booking_date: date,
        start_time: time,
        end_time: time,
        number_of_people: int,
    ) -> POSAvailabilityResult:
        # Kiểm tra slot còn khả dụng ở POS không
        ...

    @abstractmethod
    def get_available_slots(
        self,
        pos_shop_code: str,
        booking_date: date,
        total_duration_minutes: int,
        number_of_people: int,
    ) -> list[POSSlotData]:
        # Lấy danh sách slot khả dụng từ POS
        ...

    @abstractmethod
    def create_booking(self, data: POSBookingData) -> POSBookingResult:
        # Tạo booking trên POS — trả về pos_booking_code
        ...

    @abstractmethod
    def cancel_booking(self, pos_booking_code: str, reason: str | None = None) -> bool:
        # Hủy booking trên POS
        ...

    @abstractmethod
    def lookup_customer(self, phone: str) -> dict | None:
        # Tra cứu thông tin khách hàng từ POS
        ...
