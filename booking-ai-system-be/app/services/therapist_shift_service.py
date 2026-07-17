from datetime import date, time
from uuid import UUID

# Service cho TherapistShift — tạo, sửa, xem ca làm việc; kiểm tra overlap, therapist thuộc shop
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.db.models.therapist_shift import TherapistShift
from app.repositories.shift_repository import ShiftRepository
from app.repositories.shop_repository import ShopRepository
from app.repositories.therapist_repository import TherapistRepository
from app.schemas.therapist_shift import ShiftCreate, ShiftUpdate


class TherapistShiftService:
    # Khởi tạo với session và repository
    def __init__(self, session: Session):
        self.session = session
        self.repo = ShiftRepository(session)
        self.shop_repo = ShopRepository(session)
        self.therapist_repo = TherapistRepository(session)

    # Danh sách shift — kiểm tra shop tồn tại, lọc theo ngày/therapist/trạng thái
    def list(
        self,
        shop_id: UUID,
        work_date: date | None = None,
        therapist_id: UUID | None = None,
        is_active: bool | None = None,
    ) -> list[TherapistShift]:
        if not self.shop_repo.find_by_id(shop_id):
            raise AppError(404, code="SHOP_NOT_FOUND", detail="Không tìm thấy shop")
        return self.repo.find_by_shop(shop_id, work_date=work_date, therapist_id=therapist_id, is_active=is_active)

    # Chi tiết shift theo ID — báo lỗi 404 nếu không tìm thấy
    def get(self, shift_id: UUID) -> TherapistShift:
        shift = self.repo.find_by_id(shift_id)
        if not shift:
            raise AppError(404, code="SHIFT_NOT_FOUND", detail="Không tìm thấy ca làm việc")
        return shift

    # Tạo shift mới — kiểm tra shop, therapist thuộc shop, thời gian hợp lệ, không overlap
    def create(self, body: ShiftCreate) -> TherapistShift:
        try:
            if not self.shop_repo.find_by_id(body.shop_id):
                raise AppError(404, code="SHOP_NOT_FOUND", detail="Không tìm thấy shop")

            therapist = self.therapist_repo.find_by_id(body.therapist_id)
            if not therapist:
                raise AppError(404, code="THERAPIST_NOT_FOUND", detail="Không tìm thấy therapist")
            if therapist.shop_id != body.shop_id:
                raise AppError(400, code="THERAPIST_NOT_FOUND", detail="Therapist không thuộc shop này")

            if body.start_time >= body.end_time:
                raise AppError(422, code="INVALID_SHIFT_TIME_RANGE", detail="end_time phải lớn hơn start_time")

            if self.repo.exists_conflict(body.therapist_id, body.work_date, body.start_time, body.end_time):
                raise AppError(409, code="SHIFT_TIME_CONFLICT", detail="Ca làm việc bị trùng với ca đã tồn tại")

            shift = TherapistShift(**body.model_dump())
            self.repo.save(shift)
            self.session.commit()
            self.session.refresh(shift)
            return shift
        except Exception:
            self.session.rollback()
            raise

    # Cập nhật shift — kiểm tra thời gian hợp lệ, không overlap (loại trừ chính nó)
    def update(self, shift_id: UUID, body: ShiftUpdate) -> TherapistShift:
        try:
            shift = self.repo.find_by_id(shift_id)
            if not shift:
                raise AppError(404, code="SHIFT_NOT_FOUND", detail="Không tìm thấy ca làm việc")

            update_data = body.model_dump(exclude_unset=True)

            final_start = shift.start_time
            final_end = shift.end_time

            if "start_time" in update_data:
                final_start = body.start_time
            if "end_time" in update_data:
                final_end = body.end_time

            if final_start >= final_end:
                raise AppError(422, code="INVALID_SHIFT_TIME_RANGE", detail="end_time phải lớn hơn start_time")

            if self.repo.exists_conflict(shift.therapist_id, shift.work_date, final_start, final_end, exclude_shift_id=shift_id):
                raise AppError(409, code="SHIFT_TIME_CONFLICT", detail="Ca làm việc bị trùng với ca đã tồn tại")

            if "start_time" in update_data:
                shift.start_time = body.start_time
            if "end_time" in update_data:
                shift.end_time = body.end_time
            if "is_active" in update_data:
                shift.is_active = body.is_active

            self.session.commit()
            self.session.refresh(shift)
            return shift
        except Exception:
            self.session.rollback()
            raise
