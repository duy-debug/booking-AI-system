from datetime import date, time

# Service cho Available Slots — tính toán khung giờ trống, therapist khả dụng dựa trên shift và reservation
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.repositories import (
    ShopRepository,
    CourseRepository,
    ShiftRepository,
    ReservationRepository,
    BookingRepository,
)
from app.schemas.available_slot import (
    AvailableSlotMeta,
    AvailableSlotResponse,
    AvailableTherapistResponse,
)


class SlotService:
    # Khởi tạo với session và repository
    def __init__(self, session: Session):
        self.session = session
        self.shop_repo = ShopRepository(session)
        self.course_repo = CourseRepository(session)
        self.shift_repo = ShiftRepository(session)
        self.reservation_repo = ReservationRepository(session)
        self.booking_repo = BookingRepository(session)

    # Tính toán khung giờ trống — dựa trên shift therapist, course duration, booked reservation
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
        shop = self.shop_repo.find_by_id(shop_id)
        if not shop:
            raise AppError(404, code="SHOP_NOT_FOUND", detail="Không tìm thấy shop")
        if not shop.is_active:
            raise AppError(422, code="SHOP_INACTIVE", detail="Shop không hoạt động")

        main_course = self.course_repo.find_by_id(main_course_id)
        if not main_course or main_course.shop_id != shop_id:
            raise AppError(404, code="COURSE_NOT_FOUND", detail="Không tìm thấy main course")
        if main_course.course_type != "main":
            raise AppError(422, code="INVALID_COURSE_COMBO", detail="main_course_id phải là course type 'main'")

        total_duration = main_course.duration_minutes
        if addon_course_ids:
            for aid_str in addon_course_ids.split(","):
                aid_str = aid_str.strip()
                if not aid_str:
                    continue
                from uuid import UUID
                aid = UUID(aid_str)
                addon = self.course_repo.find_by_id(aid)
                if not addon or addon.shop_id != shop_id:
                    raise AppError(404, code="COURSE_NOT_FOUND", detail=f"Không tìm thấy addon course {aid_str}")
                if addon.course_type != "addon":
                    raise AppError(422, code="INVALID_COURSE_COMBO", detail=f"{aid_str} không phải course type 'addon'")
                total_duration += addon.duration_minutes

        shifts = self.shift_repo.find_available_with_therapist(shop_id, booking_date)

        filtered_shifts = []
        for shift in shifts:
            t = shift.therapist
            if not t.is_active:
                continue
            if therapist_request_type == "specific" and therapist_id:
                if str(t.therapist_id) != therapist_id:
                    continue
            if therapist_request_type == "gender" and therapist_gender:
                if t.gender != therapist_gender:
                    continue
            filtered_shifts.append(shift)

        if not filtered_shifts:
            return self._empty_slots_response(booking_date, shop_id, number_of_people)

        booked_intervals = self._build_booked_intervals(shop_id, booking_date, number_of_people)

        if number_of_people > 1:
            if len(filtered_shifts) < number_of_people:
                return self._empty_slots_response(booking_date, shop_id, number_of_people)

        if not filtered_shifts:
            return self._empty_slots_response(booking_date, shop_id, number_of_people)

        shift_intervals = [
            (self._time_to_minutes(s.start_time), self._time_to_minutes(s.end_time))
            for s in filtered_shifts
        ]
        common_start = max(s[0] for s in shift_intervals)
        common_end = min(s[1] for s in shift_intervals)

        if common_start >= common_end:
            return self._empty_slots_response(booking_date, shop_id, number_of_people)

        free_intervals = self._compute_free_intervals(common_start, common_end, booked_intervals)

        step = 15
        slots = []
        for f_start, f_end in free_intervals:
            cursor = f_start
            while cursor + total_duration <= f_end:
                slots.append(
                    AvailableSlotResponse(
                        start_time=self._minutes_to_time(cursor),
                        end_time=self._minutes_to_time(cursor + total_duration),
                        duration_minutes=total_duration,
                        available=True,
                    ).model_dump(mode="json")
                )
                cursor += step

        return {
            "data": slots,
            "meta": AvailableSlotMeta(
                booking_date=booking_date, shop_id=shop_id, number_of_people=number_of_people
            ).model_dump(mode="json"),
        }

    # Danh sách therapist khả dụng trong khung giờ — kiểm tra shift và overlap
    def list_available_therapists(
        self,
        shop_id,
        booking_date: date,
        start_time: time,
        end_time: time,
        gender: str | None = None,
    ) -> dict:
        if start_time >= end_time:
            raise AppError(422, code="INVALID_TIME_RANGE", detail="end_time phải lớn hơn start_time")

        shop = self.shop_repo.find_by_id(shop_id)
        if not shop:
            raise AppError(404, code="SHOP_NOT_FOUND", detail="Không tìm thấy shop")
        if not shop.is_active:
            raise AppError(422, code="SHOP_INACTIVE", detail="Shop không hoạt động")

        shifts = self.shift_repo.find_available_with_therapist(shop_id, booking_date)

        available_therapists = []
        for shift in shifts:
            t = shift.therapist
            if not t.is_active:
                continue
            if gender and gender != "any" and t.gender != gender:
                continue
            if shift.start_time <= start_time and shift.end_time >= end_time:
                overlap = self.reservation_repo.exists_overlap(t.therapist_id, booking_date, start_time, end_time)
                available_therapists.append(
                    AvailableTherapistResponse(
                        therapist_id=t.therapist_id,
                        shop_id=shop_id,
                        name=t.name,
                        gender=t.gender,
                        available=(not overlap),
                    ).model_dump(mode="json")
                )

        return {"data": available_therapists}

    # Response rỗng khi không có slot nào khả dụng
    def _empty_slots_response(self, booking_date: date, shop_id, number_of_people: int) -> dict:
        return {
            "data": [],
            "meta": AvailableSlotMeta(
                booking_date=booking_date, shop_id=shop_id, number_of_people=number_of_people
            ).model_dump(mode="json"),
        }

    # Xây danh sách khoảng thời gian đã được đặt — gộp các interval chồng lấn
    def _build_booked_intervals(self, shop_id, booking_date: date, number_of_people: int) -> list[tuple[int, int]]:
        booked_intervals = []
        if number_of_people == 1:
            reservations = self.reservation_repo.find_by_shop_date_non_cancelled(shop_id, booking_date)
            for res in reservations:
                booked_intervals.append(
                    (self._time_to_minutes(res.start_time), self._time_to_minutes(res.end_time))
                )
        else:
            bookings = self.booking_repo.find_by_shop_date_non_cancelled(shop_id, booking_date)
            for bk in bookings:
                booked_intervals.append(
                    (self._time_to_minutes(bk.start_time), self._time_to_minutes(bk.end_time))
                )

        if booked_intervals:
            booked_intervals.sort()
            merged = [booked_intervals[0]]
            for start, end in booked_intervals[1:]:
                if start <= merged[-1][1]:
                    merged[-1] = (merged[-1][0], max(merged[-1][1], end))
                else:
                    merged.append((start, end))
            booked_intervals = merged

        return booked_intervals

    # Tính khoảng thời gian trống — trừ booked_intervals khỏi common interval
    def _compute_free_intervals(self, common_start: int, common_end: int, booked_intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
        free_intervals = [(common_start, common_end)]
        for b_start, b_end in booked_intervals:
            new_free = []
            for f_start, f_end in free_intervals:
                if b_end <= f_start or b_start >= f_end:
                    new_free.append((f_start, f_end))
                else:
                    if b_start > f_start:
                        new_free.append((f_start, b_start))
                    if b_end < f_end:
                        new_free.append((b_end, f_end))
            free_intervals = new_free
        return free_intervals

    # Chuyển đổi time sang số phút từ đầu ngày
    @staticmethod
    def _time_to_minutes(t: time) -> int:
        return t.hour * 60 + t.minute

    # Chuyển đổi số phút từ đầu ngày sang time
    @staticmethod
    def _minutes_to_time(m: int) -> time:
        return time(m // 60, m % 60)
