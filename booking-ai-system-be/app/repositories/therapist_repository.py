# Repository cho Therapist — CRUD + kiểm tra pos_therapist_code duy nhất trong shop
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.therapist import Therapist


class TherapistRepository:
    # Khởi tạo với session database
    def __init__(self, session: Session):
        self.session = session

    # Tìm therapist theo ID
    def find_by_id(self, therapist_id: UUID) -> Therapist | None:
        return self.session.get(Therapist, therapist_id)

    # Danh sách therapist trong shop — lọc theo trạng thái hoạt động
    def find_by_shop(self, shop_id: UUID, is_active: bool | None = None) -> list[Therapist]:
        stmt = select(Therapist).where(Therapist.shop_id == shop_id)
        if is_active is not None:
            stmt = stmt.where(Therapist.is_active == is_active)
        stmt = stmt.order_by(Therapist.name)
        return list(self.session.scalars(stmt).all())

    # Kiểm tra pos_therapist_code đã tồn tại trong shop chưa
    def exists_by_pos_code_in_shop(self, pos_code: str, shop_id: UUID) -> bool:
        stmt = (
            select(Therapist.therapist_id)
            .where(Therapist.shop_id == shop_id, Therapist.pos_therapist_code == pos_code)
            .limit(1)
        )
        return self.session.scalar(stmt) is not None

    # Danh sách therapist đang hoạt động trong shop — có giới hạn số lượng
    def find_active_by_shop(self, shop_id: UUID, limit: int | None = None) -> list[Therapist]:
        stmt = select(Therapist).where(Therapist.shop_id == shop_id, Therapist.is_active == True)
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.session.scalars(stmt).all())

    # Lưu therapist mới — add + flush
    def save(self, therapist: Therapist) -> Therapist:
        self.session.add(therapist)
        self.session.flush()
        return therapist
