from uuid import UUID

# Service cho Therapist — tạo, sửa, xem danh sách therapist trong shop; kiểm tra shop tồn tại
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.db.models.therapist import Therapist
from app.repositories.therapist_repository import TherapistRepository
from app.repositories.shop_repository import ShopRepository
from app.schemas.therapist import TherapistCreate, TherapistUpdate


class TherapistService:
    # Khởi tạo với session và repository
    def __init__(self, session: Session):
        self.session = session
        self.repo = TherapistRepository(session)
        self.shop_repo = ShopRepository(session)

    # Danh sách therapist trong shop — kiểm tra shop tồn tại, lọc theo trạng thái
    def list(self, shop_id: UUID, is_active: bool | None = None) -> list[Therapist]:
        if not self.shop_repo.find_by_id(shop_id):
            raise AppError(404, code="SHOP_NOT_FOUND", detail="Không tìm thấy shop")
        return self.repo.find_by_shop(shop_id, is_active=is_active)

    # Chi tiết therapist theo ID — báo lỗi 404 nếu không tìm thấy
    def get(self, therapist_id: UUID) -> Therapist:
        therapist = self.repo.find_by_id(therapist_id)
        if not therapist:
            raise AppError(404, code="THERAPIST_NOT_FOUND", detail="Không tìm thấy therapist")
        return therapist

    # Tạo therapist mới trong shop — kiểm tra pos_therapist_code duy nhất
    def create(self, shop_id: UUID, body: TherapistCreate) -> Therapist:
        try:
            if not self.shop_repo.find_by_id(shop_id):
                raise AppError(404, code="SHOP_NOT_FOUND", detail="Không tìm thấy shop")

            if self.repo.exists_by_pos_code_in_shop(body.pos_therapist_code, shop_id):
                raise AppError(409, code="POS_THERAPIST_CODE_ALREADY_EXISTS", detail="pos_therapist_code đã tồn tại trong shop")

            therapist = Therapist(shop_id=shop_id, **body.model_dump())
            self.repo.save(therapist)
            self.session.commit()
            self.session.refresh(therapist)
            return therapist
        except Exception:
            self.session.rollback()
            raise

    # Cập nhật therapist — chỉ ghi các trường được gửi lên
    def update(self, therapist_id: UUID, body: TherapistUpdate) -> Therapist:
        try:
            therapist = self.repo.find_by_id(therapist_id)
            if not therapist:
                raise AppError(404, code="THERAPIST_NOT_FOUND", detail="Không tìm thấy therapist")

            update_data = body.model_dump(exclude_unset=True)
            if "name" in update_data:
                therapist.name = body.name
            if "gender" in update_data:
                therapist.gender = body.gender
            if "is_active" in update_data:
                therapist.is_active = body.is_active

            self.session.commit()
            self.session.refresh(therapist)
            return therapist
        except Exception:
            self.session.rollback()
            raise
