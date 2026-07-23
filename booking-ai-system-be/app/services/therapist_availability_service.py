from dataclasses import dataclass
from datetime import date, time
from uuid import UUID

from sqlalchemy.orm import Session

from app.repositories import ReservationRepository, ShiftRepository, ShopRepository
from app.core.time_ranges import intervals_overlap_with_break


@dataclass(frozen=True)
class AvailabilityDayContext:
    active_shifts: list
    therapists: dict
    shifts_by_therapist: dict
    blocked_by_therapist: dict
    reservations_by_therapist: dict
    break_minutes: int = 0


@dataclass(frozen=True)
class TherapistAvailabilityResult:
    available_therapists: list
    covering_therapist_count: int
    busy_therapist_count: int
    blocked_therapist_count: int

    # Trả số therapist thực sự khả dụng sau khi đã lọc ca làm, blocked range và reservation overlap.
    @property
    def available_therapist_count(self) -> int:
        return len(self.available_therapists)


class TherapistAvailabilityService:
    # Khởi tạo repository ca làm và reservation dùng cho mọi phép đánh giá availability.
    def __init__(self, session: Session):
        self.shift_repo = ShiftRepository(session)
        self.reservation_repo = ReservationRepository(session)
        self.shop_repo = ShopRepository(session)

    # Đánh giá danh sách therapist phục vụ trọn khoảng giờ theo request type và tùy chọn khóa shift.
    def evaluate(
        self,
        shop_id: UUID,
        booking_date: date,
        start_time: time,
        end_time: time,
        request_type: str = "none",
        requested_therapist_id: UUID | str | None = None,
        requested_gender: str | None = None,
        lock_shifts: bool = False,
        context: AvailabilityDayContext | None = None,
        exclude_booking_id: UUID | None = None,
        break_minutes: int | None = None,
    ) -> TherapistAvailabilityResult:
        if context is not None:
            return self._evaluate_context(
                context=context,
                start_time=start_time,
                end_time=end_time,
                request_type=request_type,
                requested_therapist_id=requested_therapist_id,
                requested_gender=requested_gender,
            )

        effective_break_minutes = break_minutes
        if effective_break_minutes is None:
            shop_repo = getattr(self, "shop_repo", None)
            shop = shop_repo.find_by_id(shop_id) if shop_repo else None
            effective_break_minutes = shop.therapist_break_minutes if shop else 0

        covering = {}
        for shift in self.shift_repo.find_available_with_therapist(
            shop_id, booking_date, for_update=lock_shifts
        ):
            therapist = shift.therapist
            if not therapist or not therapist.is_active or therapist.shop_id != shop_id:
                continue
            if request_type == "specific" and requested_therapist_id:
                if str(therapist.therapist_id) != str(requested_therapist_id):
                    continue
            if request_type == "gender" and requested_gender:
                if therapist.gender != requested_gender:
                    continue
            if shift.start_time <= start_time and shift.end_time >= end_time:
                covering[therapist.therapist_id] = therapist

        available = []
        busy_count = 0
        blocked_count = 0
        for therapist_id, therapist in covering.items():
            if self.shift_repo.exists_inactive_overlap(
                therapist_id, booking_date, start_time, end_time
            ):
                blocked_count += 1
                continue
            overlap_kwargs = (
                {"exclude_booking_id": exclude_booking_id}
                if exclude_booking_id is not None
                else {}
            )
            if effective_break_minutes:
                overlap_kwargs["break_minutes"] = effective_break_minutes
            if self.reservation_repo.exists_overlap(
                therapist_id, booking_date, start_time, end_time, **overlap_kwargs
            ):
                busy_count += 1
                continue
            available.append(therapist)

        return TherapistAvailabilityResult(
            available_therapists=available,
            covering_therapist_count=len(covering),
            busy_therapist_count=busy_count,
            blocked_therapist_count=blocked_count,
        )

    # Nạp trước ca làm, blocked range và reservation của một ngày để tái sử dụng khi tính nhiều slot.
    def load_day_context(
        self, shop_id: UUID, booking_date: date
    ) -> AvailabilityDayContext:
        active_shifts = self.shift_repo.find_available_with_therapist(
            shop_id, booking_date
        )
        blocked_shifts = self.shift_repo.find_by_shop(
            shop_id, work_date=booking_date, is_active=False
        )
        reservations = self.reservation_repo.find_by_shop_date_non_cancelled(
            shop_id, booking_date
        )
        shop_repo = getattr(self, "shop_repo", None)
        shop = shop_repo.find_by_id(shop_id) if shop_repo else None

        therapists = {}
        shifts_by_therapist = {}
        for shift in active_shifts:
            therapist = shift.therapist
            if not therapist or not therapist.is_active or therapist.shop_id != shop_id:
                continue
            therapist_id = therapist.therapist_id
            therapists[therapist_id] = therapist
            shifts_by_therapist.setdefault(therapist_id, []).append(
                (shift.start_time, shift.end_time)
            )

        blocked_by_therapist = {}
        for shift in blocked_shifts:
            blocked_by_therapist.setdefault(shift.therapist_id, []).append(
                (shift.start_time, shift.end_time)
            )

        reservations_by_therapist = {}
        for reservation in reservations:
            reservations_by_therapist.setdefault(
                reservation.therapist_id, []
            ).append((reservation.start_time, reservation.end_time))

        return AvailabilityDayContext(
            active_shifts=active_shifts,
            therapists=therapists,
            shifts_by_therapist=shifts_by_therapist,
            blocked_by_therapist=blocked_by_therapist,
            reservations_by_therapist=reservations_by_therapist,
            break_minutes=shop.therapist_break_minutes if shop else 0,
        )

    # Đánh giá availability hoàn toàn trên dữ liệu context đã nạp, tránh phát sinh truy vấn cho từng slot.
    @staticmethod
    def _evaluate_context(
        context: AvailabilityDayContext,
        start_time: time,
        end_time: time,
        request_type: str,
        requested_therapist_id: UUID | str | None,
        requested_gender: str | None,
    ) -> TherapistAvailabilityResult:
        covering = {}
        for therapist_id, therapist in context.therapists.items():
            if request_type == "specific" and requested_therapist_id:
                if str(therapist_id) != str(requested_therapist_id):
                    continue
            if request_type == "gender" and requested_gender:
                if therapist.gender != requested_gender:
                    continue
            if any(
                shift_start <= start_time and shift_end >= end_time
                for shift_start, shift_end in context.shifts_by_therapist.get(
                    therapist_id, []
                )
            ):
                covering[therapist_id] = therapist

        available = []
        busy_count = 0
        blocked_count = 0
        for therapist_id, therapist in covering.items():
            if TherapistAvailabilityService._has_overlap(
                context.blocked_by_therapist.get(therapist_id, []),
                start_time,
                end_time,
            ):
                blocked_count += 1
                continue
            if TherapistAvailabilityService._has_overlap(
                context.reservations_by_therapist.get(therapist_id, []),
                start_time,
                end_time,
                context.break_minutes,
            ):
                busy_count += 1
                continue
            available.append(therapist)

        return TherapistAvailabilityResult(
            available_therapists=available,
            covering_therapist_count=len(covering),
            busy_therapist_count=busy_count,
            blocked_therapist_count=blocked_count,
        )

    # Kiểm tra một khoảng giờ có giao với bất kỳ khoảng đã tồn tại nào theo quy tắc đầu đóng cuối mở.
    @staticmethod
    def _has_overlap(
        intervals: list[tuple[time, time]],
        start_time: time,
        end_time: time,
        break_minutes: int = 0,
    ) -> bool:
        return any(
            intervals_overlap_with_break(
                existing_start,
                existing_end,
                start_time,
                end_time,
                break_minutes,
            )
            for existing_start, existing_end in intervals
        )

    # Cung cấp API rút gọn chỉ trả danh sách therapist từ kết quả đánh giá đầy đủ.
    def find_available_therapists(self, **kwargs) -> list:
        return self.evaluate(**kwargs).available_therapists
