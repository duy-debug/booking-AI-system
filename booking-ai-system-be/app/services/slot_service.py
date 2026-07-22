from datetime import date, time
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.repositories import CourseRepository, ReservationRepository, ShopRepository
from app.schemas.available_slot import (
    AvailableSlotMeta,
    AvailableSlotResponse,
    AvailableTherapistResponse,
)
import app.services.booking_time as booking_time
from app.services.therapist_availability_service import TherapistAvailabilityService


class SlotService:
    # Khởi tạo các repository và availability service dùng chung cho nghiệp vụ tra cứu slot.
    def __init__(self, session: Session):
        self.session = session
        self.shop_repo = ShopRepository(session)
        self.course_repo = CourseRepository(session)
        self.reservation_repo = ReservationRepository(session)
        self.availability_service = TherapistAvailabilityService(session)

    # Tạo danh sách slot 15 phút, tính thời lượng course và đánh giá số therapist đáp ứng từng khung giờ.
    def list_available_slots(
        self,
        shop_id,
        booking_date: date,
        number_of_people: int,
        main_course_id,
        addon_course_ids: str | None = None,
        therapist_request_type: str | None = None,
        therapist_id: str | None = None,
        therapist_gender: str | None = None,
    ) -> dict:
        if number_of_people > 1 and therapist_request_type == "specific":
            raise AppError(
                422,
                code="GROUP_BOOKING_CANNOT_REQUEST_SPECIFIC_THERAPIST",
                detail="Booking nhóm không thể chỉ định một therapist cụ thể.",
            )

        shop = self.shop_repo.find_by_id(shop_id)
        if not shop:
            raise AppError(404, code="SHOP_NOT_FOUND", detail="Không tìm thấy shop")
        if not shop.is_active:
            raise AppError(422, code="SHOP_INACTIVE", detail="Shop không hoạt động")

        total_duration = self._course_duration(
            shop_id, main_course_id, addon_course_ids
        )
        request_type = therapist_request_type or "none"
        context = self.availability_service.load_day_context(
            shop_id, booking_date
        )
        shifts = [
            shift
            for shift in context.active_shifts
            if self._shift_matches_request(
                shift, shop_id, request_type, therapist_id, therapist_gender
            )
        ]
        if not shifts:
            return self._empty_slots_response(
                booking_date, shop_id, number_of_people
            )

        step = 15
        cursor = min(self._time_to_minutes(s.start_time) for s in shifts)
        last_end = max(self._time_to_minutes(s.end_time) for s in shifts)
        now = booking_time.current_utc_time()
        slots = []
        while cursor + total_duration <= last_end:
            slot_start = self._minutes_to_time(cursor)
            slot_end = self._minutes_to_time(cursor + total_duration)
            result = self.availability_service.evaluate(
                shop_id=shop_id,
                booking_date=booking_date,
                start_time=slot_start,
                end_time=slot_end,
                request_type=request_type,
                requested_therapist_id=therapist_id,
                requested_gender=therapist_gender,
                context=context,
            )
            window = booking_time.booking_start_window(
                booking_date, slot_start, now=now
            )
            reason_code, message = self._unavailable_reason(
                number_of_people, result, window
            )
            priority_available = (
                reason_code == "SLOT_CONFLICT"
                and number_of_people == 1
                and request_type == "specific"
                and therapist_id is not None
                and self._can_rebalance_specific_assignment(
                    shop_id=shop_id,
                    booking_date=booking_date,
                    start_time=slot_start,
                    end_time=slot_end,
                    requested_therapist_id=UUID(str(therapist_id)),
                    context=context,
                )
            )
            available = (
                result.available_therapist_count >= number_of_people
                or priority_available
            )
            if priority_available:
                reason_code, message = None, None
            if reason_code:
                available = False
            slots.append(
                AvailableSlotResponse(
                    start_time=slot_start,
                    end_time=slot_end,
                    duration_minutes=total_duration,
                    available=available,
                    reason_code=None if available else reason_code,
                    message=None if available else message,
                    available_therapist_count=max(
                        result.available_therapist_count,
                        1 if priority_available else 0,
                    ),
                    required_therapist_count=number_of_people,
                ).model_dump(mode="json")
            )
            cursor += step

        return {
            "data": slots,
            "meta": AvailableSlotMeta(
                booking_date=booking_date,
                shop_id=shop_id,
                number_of_people=number_of_people,
            ).model_dump(mode="json"),
        }

    # Dự đoán yêu cầu specific có thể thay thế một reservation auto mà không làm thay đổi dữ liệu hiện tại.
    def _can_rebalance_specific_assignment(
        self,
        shop_id: UUID,
        booking_date: date,
        start_time: time,
        end_time: time,
        requested_therapist_id: UUID,
        context,
    ) -> bool:
        overlaps = self.reservation_repo.find_overlaps(
            requested_therapist_id, booking_date, start_time, end_time
        )
        if len(overlaps) != 1 or overlaps[0].assignment_source != "auto":
            return False

        displaced = overlaps[0]
        displaced_booking = displaced.booking
        replacement = self.availability_service.evaluate(
            shop_id=shop_id,
            booking_date=booking_date,
            start_time=displaced.start_time,
            end_time=displaced.end_time,
            request_type=(
                "gender"
                if displaced_booking.therapist_request_type == "gender"
                else "none"
            ),
            requested_gender=displaced_booking.requested_gender,
            context=context,
        )
        return any(
            therapist.therapist_id != requested_therapist_id
            for therapist in replacement.available_therapists
        )

    # Liệt kê therapist có ca bao phủ toàn bộ khoảng giờ, không bị block và không trùng reservation active.
    def list_available_therapists(
        self,
        shop_id,
        booking_date: date,
        start_time: time,
        end_time: time,
        gender: str | None = None,
    ) -> dict:
        if start_time >= end_time:
            raise AppError(
                422,
                code="INVALID_TIME_RANGE",
                detail="end_time phải lớn hơn start_time",
            )
        shop = self.shop_repo.find_by_id(shop_id)
        if not shop:
            raise AppError(404, code="SHOP_NOT_FOUND", detail="Không tìm thấy shop")
        if not shop.is_active:
            raise AppError(422, code="SHOP_INACTIVE", detail="Shop không hoạt động")

        context = self.availability_service.load_day_context(shop_id, booking_date)
        result = self.availability_service.evaluate(
            shop_id=shop_id,
            booking_date=booking_date,
            start_time=start_time,
            end_time=end_time,
            request_type="gender" if gender and gender != "any" else "none",
            requested_gender=gender if gender != "any" else None,
            context=context,
        )
        return {
            "data": [
                AvailableTherapistResponse(
                    therapist_id=t.therapist_id,
                    shop_id=shop_id,
                    name=t.name,
                    gender=t.gender,
                    available=True,
                ).model_dump(mode="json")
                for t in result.available_therapists
            ]
        }

    # Kiểm tra main course và add-on thuộc đúng shop, sau đó cộng tổng thời lượng cần giữ slot.
    def _course_duration(
        self, shop_id: UUID, main_course_id: UUID, addon_course_ids: str | None
    ) -> int:
        main_course = self.course_repo.find_by_id(main_course_id)
        if not main_course or main_course.shop_id != shop_id:
            raise AppError(404, code="COURSE_NOT_FOUND", detail="Không tìm thấy main course")
        if main_course.course_type != "main":
            raise AppError(
                422,
                code="INVALID_COURSE_COMBO",
                detail="main_course_id phải là course type 'main'",
            )
        total = main_course.duration_minutes
        for raw_id in (addon_course_ids or "").split(","):
            raw_id = raw_id.strip()
            if not raw_id:
                continue
            addon = self.course_repo.find_by_id(UUID(raw_id))
            if not addon or addon.shop_id != shop_id:
                raise AppError(
                    404, code="COURSE_NOT_FOUND", detail=f"Không tìm thấy addon course {raw_id}"
                )
            if addon.course_type != "addon":
                raise AppError(
                    422,
                    code="INVALID_COURSE_COMBO",
                    detail=f"{raw_id} không phải course type 'addon'",
                )
            total += addon.duration_minutes
        return total

    # Kiểm tra shift có thuộc shop, therapist còn hoạt động và thỏa yêu cầu specific hoặc gender hay không.
    @staticmethod
    def _shift_matches_request(
        shift,
        shop_id: UUID,
        request_type: str,
        therapist_id: str | None,
        therapist_gender: str | None,
    ) -> bool:
        therapist = shift.therapist
        if not therapist or not therapist.is_active or therapist.shop_id != shop_id:
            return False
        if request_type == "specific" and therapist_id:
            return str(therapist.therapist_id) == str(therapist_id)
        if request_type == "gender" and therapist_gender:
            return therapist.gender == therapist_gender
        return True

    # Chuyển kết quả availability và cửa sổ thời gian thành mã cùng thông báo không khả dụng phù hợp.
    @staticmethod
    def _unavailable_reason(number_of_people, result, window) -> tuple[str | None, str | None]:
        if window.start_at < window.now:
            return "START_IN_PAST", "Không thể tạo booking trong quá khứ."
        if window.start_at < window.earliest_allowed_at:
            return "START_TOO_SOON", "Thời gian bắt đầu quá sát giờ hiện tại."
        if result.available_therapist_count >= number_of_people:
            return None, None
        if result.covering_therapist_count == 0:
            return "OUTSIDE_SHIFT", "Không có therapist có ca bao phủ toàn bộ khung giờ."
        if number_of_people > 1:
            return (
                "INSUFFICIENT_AVAILABLE_THERAPISTS",
                f"Không đủ therapist rảnh đồng thời cho nhóm {number_of_people} người.",
            )
        return "SLOT_CONFLICT", "Therapist không rảnh trong khung giờ này."

    # Tạo response rỗng nhưng vẫn giữ metadata ngày, shop và số người khi không có ca phù hợp.
    @staticmethod
    def _empty_slots_response(booking_date: date, shop_id, number_of_people: int) -> dict:
        return {
            "data": [],
            "meta": AvailableSlotMeta(
                booking_date=booking_date,
                shop_id=shop_id,
                number_of_people=number_of_people,
            ).model_dump(mode="json"),
        }

    # Quy đổi đối tượng time sang tổng số phút tính từ đầu ngày để thuận tiện duyệt slot.
    @staticmethod
    def _time_to_minutes(value: time) -> int:
        return value.hour * 60 + value.minute

    # Chuyển tổng số phút trong ngày trở lại đối tượng time dùng cho truy vấn availability.
    @staticmethod
    def _minutes_to_time(value: int) -> time:
        return time(value // 60, value % 60)
