from uuid import UUID

# Service cho CustomerRestriction — tạo, sửa, xem restriction; kiểm tra active duplicate khi reactivate
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.db.models.customer_restriction import CustomerRestriction
from app.repositories.restriction_repository import RestrictionRepository
from app.schemas.customer_restriction import RestrictionCreate, RestrictionUpdate


class RestrictionService:
    # Khởi tạo với session và repository
    def __init__(self, session: Session):
        self.session = session
        self.repo = RestrictionRepository(session)

    # Danh sách restriction — lọc theo phone và trạng thái active
    def list(self, phone: str | None = None, is_active: bool | None = None) -> list[CustomerRestriction]:
        return self.repo.find_all(phone=phone, is_active=is_active)

    # Chi tiết restriction theo ID — báo lỗi 404 nếu không tìm thấy
    def get(self, restriction_id: UUID) -> CustomerRestriction:
        restriction = self.repo.find_by_id(restriction_id)
        if not restriction:
            raise AppError(404, code="CUSTOMER_RESTRICTION_NOT_FOUND", detail="Không tìm thấy restriction")
        return restriction

    # Tạo restriction mới — kiểm tra không có restriction active cho phone đó
    def create(self, body: RestrictionCreate) -> CustomerRestriction:
        try:
            if body.is_active:
                existing = self.repo.find_active_by_phone(body.phone)
                if existing:
                    raise AppError(409, code="CUSTOMER_RESTRICTION_ALREADY_EXISTS", detail="Phone đã có restriction còn hiệu lực")

            restriction = CustomerRestriction(**body.model_dump())
            self.repo.save(restriction)
            self.session.commit()
            self.session.refresh(restriction)
            return restriction
        except Exception:
            self.session.rollback()
            raise

    # Cập nhật restriction — kiểm tra conflict khi reactivate (loại trừ chính nó)
    def update(self, restriction_id: UUID, body: RestrictionUpdate) -> CustomerRestriction:
        try:
            restriction = self.repo.find_by_id(restriction_id)
            if not restriction:
                raise AppError(404, code="CUSTOMER_RESTRICTION_NOT_FOUND", detail="Không tìm thấy restriction")

            update_data = body.model_dump(exclude_unset=True)

            final_is_active = restriction.is_active
            if "is_active" in update_data:
                final_is_active = body.is_active

            if final_is_active:
                conflict = self.repo.find_active_by_phone(restriction.phone)
                if conflict and conflict.restriction_id != restriction_id:
                    raise AppError(409, code="CUSTOMER_RESTRICTION_ALREADY_EXISTS", detail="Phone đã có restriction còn hiệu lực")

            if "reason" in update_data:
                restriction.reason = body.reason
            if "is_active" in update_data:
                restriction.is_active = body.is_active

            self.session.commit()
            self.session.refresh(restriction)
            return restriction
        except Exception:
            self.session.rollback()
            raise
