# Repository cho TherapistShift — CRUD + kiểm tra overlap giờ làm việc
from datetime import date, time
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.db.models.therapist_shift import TherapistShift


class ShiftRepository:
    # Khởi tạo với session database
    def __init__(self, session: Session):
        self.session = session

    # Tìm shift theo ID
    def find_by_id(self, shift_id: UUID) -> TherapistShift | None:
        return self.session.get(TherapistShift, shift_id)

    # Danh sách shift trong shop — lọc theo ngày, therapist, trạng thái
    def find_by_shop(
        self,
        shop_id: UUID,
        work_date: date | None = None,
        therapist_id: UUID | None = None,
        is_active: bool | None = None,
    ) -> list[TherapistShift]:
        stmt = select(TherapistShift).where(TherapistShift.shop_id == shop_id)
        if work_date is not None:
            stmt = stmt.where(TherapistShift.work_date == work_date)
        if therapist_id is not None:
            stmt = stmt.where(TherapistShift.therapist_id == therapist_id)
        if is_active is not None:
            stmt = stmt.where(TherapistShift.is_active == is_active)
        stmt = stmt.order_by(TherapistShift.work_date, TherapistShift.start_time)
        return list(self.session.scalars(stmt).all())

    # Shift đang hoạt động theo shop + ngày — kèm thông tin therapist
    def find_available_with_therapist(
        self, shop_id: UUID, work_date: date, *, for_update: bool = False
    ) -> list[TherapistShift]:
        stmt = (
            select(TherapistShift)
            .where(
                TherapistShift.shop_id == shop_id,
                TherapistShift.work_date == work_date,
                TherapistShift.is_active == True,
            )
            .options(joinedload(TherapistShift.therapist))
            .order_by(TherapistShift.therapist_id, TherapistShift.shift_id)
        )
        if for_update:
            stmt = stmt.with_for_update(of=TherapistShift)
        return list(self.session.scalars(stmt).all())

    # Shift của therapist theo ngày — chỉ lấy active
    def find_by_therapist_and_date(self, therapist_id: UUID, work_date: date) -> TherapistShift | None:
        stmt = select(TherapistShift).where(
            TherapistShift.therapist_id == therapist_id,
            TherapistShift.work_date == work_date,
            TherapistShift.is_active == True,
        )
        return self.session.scalar(stmt)

    # Kiểm tra xung đột giờ làm — có loại trừ shift_id khi cập nhật
    def exists_conflict(
        self,
        therapist_id: UUID,
        work_date: date,
        start_time: time,
        end_time: time,
        exclude_shift_id: UUID | None = None,
    ) -> bool:
        stmt = select(TherapistShift.shift_id).where(
            TherapistShift.therapist_id == therapist_id,
            TherapistShift.work_date == work_date,
            TherapistShift.start_time < end_time,
            TherapistShift.end_time > start_time,
            TherapistShift.is_active == True,
        )
        if exclude_shift_id is not None:
            stmt = stmt.where(TherapistShift.shift_id != exclude_shift_id)
        stmt = stmt.limit(1)
        return self.session.scalar(stmt) is not None

    # Kiểm tra một inactive shift có chặn bất kỳ phần nào của khoảng thời gian yêu cầu hay không.
    def exists_inactive_overlap(
        self,
        therapist_id: UUID,
        work_date: date,
        start_time: time,
        end_time: time,
    ) -> bool:
        stmt = (
            select(TherapistShift.shift_id)
            .where(
                TherapistShift.therapist_id == therapist_id,
                TherapistShift.work_date == work_date,
                TherapistShift.start_time < end_time,
                TherapistShift.end_time > start_time,
                TherapistShift.is_active == False,
            )
            .limit(1)
        )
        return self.session.scalar(stmt) is not None

    # Lưu shift mới — add + flush
    def save(self, shift: TherapistShift) -> TherapistShift:
        self.session.add(shift)
        self.session.flush()
        return shift
