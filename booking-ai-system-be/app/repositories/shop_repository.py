# Repository cho Shop — CRUD + kiểm tra shop_code, pos_shop_code duy nhất
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.shop import Shop


class ShopRepository:
    # Khởi tạo với session database
    def __init__(self, session: Session):
        self.session = session

    # Tìm shop theo ID
    def find_by_id(self, shop_id: UUID) -> Shop | None:
        return self.session.get(Shop, shop_id)

    # Danh sách shop — lọc theo trạng thái hoạt động, sắp xếp theo tên
    def find_all(self, is_active: bool | None = None, order_by: str = "name") -> list[Shop]:
        stmt = select(Shop)
        if is_active is not None:
            stmt = stmt.where(Shop.is_active == is_active)
        order_col = getattr(Shop, order_by, Shop.name)
        stmt = stmt.order_by(order_col)
        return list(self.session.scalars(stmt).all())

    # Kiểm tra shop_code đã tồn tại chưa
    def exists_by_code(self, code: str) -> bool:
        stmt = select(Shop.shop_id).where(Shop.shop_code == code).limit(1)
        return self.session.scalar(stmt) is not None

    # Kiểm tra pos_shop_code đã tồn tại chưa
    def exists_by_pos_code(self, pos_code: str) -> bool:
        stmt = select(Shop.shop_id).where(Shop.pos_shop_code == pos_code).limit(1)
        return self.session.scalar(stmt) is not None

    # Lưu shop mới — add + flush
    def save(self, shop: Shop) -> Shop:
        self.session.add(shop)
        self.session.flush()
        return shop
