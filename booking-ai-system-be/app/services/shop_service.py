from __future__ import annotations

# Service cho Shop — tạo, sửa, xem danh sách shop; kiểm tra mã duy nhất trước khi ghi
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.db.models.shop import Shop
from app.repositories.shop_repository import ShopRepository
from app.schemas.shop import (
    PublicShopListResponse,
    PublicShopResponse,
    ShopCreate,
    ShopUpdate,
)


class ShopService:
    # Khởi tạo với session và repository
    def __init__(self, session: Session):
        self.session = session
        self.repo = ShopRepository(session)

    # Danh sách shop — lọc theo trạng thái hoạt động
    def list(self, is_active: bool | None = None) -> list[Shop]:
        return self.repo.find_all(is_active=is_active, order_by="shop_code")

    # Trả danh sách shop public dưới dạng DTO kèm HATEOAS links, không để ORM đi lên router.
    def list_public(self, is_active: bool = True) -> list[PublicShopListResponse]:
        shops = self.repo.find_all(is_active=is_active, order_by="name")
        return [
            PublicShopListResponse.model_validate({
                "shop_id": shop.shop_id,
                "shop_code": shop.shop_code,
                "name": shop.name,
                "address": shop.address,
                "phone": shop.phone,
                "links": {
                    "self": f"/api/shops/{shop.shop_id}",
                    "courses": f"/api/shops/{shop.shop_id}/courses",
                    "available_slots": f"/api/shops/{shop.shop_id}/available-slots",
                },
            })
            for shop in shops
        ]

    # Trả chi tiết shop public dưới dạng Pydantic DTO không chứa field nội bộ.
    def get_public(self, shop_id) -> PublicShopResponse:
        return PublicShopResponse.model_validate(self.get(shop_id))

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
            self.repo.refresh(shop)
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
            if "therapist_break_minutes" in update_data:
                shop.therapist_break_minutes = body.therapist_break_minutes

            self.session.commit()
            self.repo.refresh(shop)
            return shop
        except Exception:
            self.session.rollback()
            raise
