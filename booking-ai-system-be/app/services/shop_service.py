# Service cho Shop — tạo, sửa, xem danh sách shop; kiểm tra mã duy nhất trước khi ghi
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.db.models.shop import Shop
from app.repositories.shop_repository import ShopRepository
from app.schemas.shop import ShopCreate, ShopUpdate


class ShopService:
    # Khởi tạo với session và repository
    def __init__(self, session: Session):
        self.session = session
        self.repo = ShopRepository(session)

    # Danh sách shop — lọc theo trạng thái hoạt động
    def list(self, is_active: bool | None = None) -> list[Shop]:
        return self.repo.find_all(is_active=is_active, order_by="shop_code")

    # Chi tiết shop theo ID — báo lỗi 404 nếu không tìm thấy
    def get(self, shop_id) -> Shop:
        shop = self.repo.find_by_id(shop_id)
        if not shop:
            raise AppError(404, code="SHOP_NOT_FOUND", detail="Không tìm thấy shop")
        return shop

    # Tạo shop mới — kiểm tra shop_code và pos_shop_code duy nhất
    def create(self, body: ShopCreate) -> Shop:
        try:
            if self.repo.exists_by_code(body.shop_code):
                raise AppError(409, code="SHOP_CODE_ALREADY_EXISTS", detail="shop_code đã tồn tại")
            if self.repo.exists_by_pos_code(body.pos_shop_code):
                raise AppError(409, code="POS_SHOP_CODE_ALREADY_EXISTS", detail="pos_shop_code đã tồn tại")

            shop = Shop(**body.model_dump())
            self.repo.save(shop)
            self.session.commit()
            self.session.refresh(shop)
            return shop
        except Exception:
            self.session.rollback()
            raise

    # Cập nhật shop — chỉ ghi các trường được gửi lên
    def update(self, shop_id, body: ShopUpdate) -> Shop:
        try:
            shop = self.repo.find_by_id(shop_id)
            if not shop:
                raise AppError(404, code="SHOP_NOT_FOUND", detail="Không tìm thấy shop")

            update_data = body.model_dump(exclude_unset=True)
            if "name" in update_data:
                shop.name = body.name
            if "address" in update_data:
                shop.address = body.address
            if "phone" in update_data:
                shop.phone = body.phone
            if "is_active" in update_data:
                shop.is_active = body.is_active

            self.session.commit()
            self.session.refresh(shop)
            return shop
        except Exception:
            self.session.rollback()
            raise
