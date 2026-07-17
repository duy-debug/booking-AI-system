from fastapi import APIRouter, Depends, Query
from app.core.exceptions import AppError
from app.core.auth import get_current_admin
from sqlalchemy.orm import Session

from app.api.deps import get_db, parse_uuid
from app.schemas.shop import ShopCreate, AdminShopResponse, ShopUpdate
from app.services.shop_service import ShopService

router = APIRouter(prefix="/api/admin/shops", tags=["admin-shops"], dependencies=[Depends(get_current_admin)])


# Danh sách shop — lọc theo trạng thái hoạt động
@router.get("")
def list_shops(
    is_active: bool | None = Query(None),
    db: Session = Depends(get_db),
):
    service = ShopService(db)
    shops = service.list(is_active=is_active)
    return {
        "data": [AdminShopResponse.model_validate(s).model_dump(mode="json") for s in shops],
        "meta": {"total": len(shops)},
    }


# Tạo shop mới — shop_code và pos_shop_code phải duy nhất
@router.post("", status_code=201)
def create_shop(body: ShopCreate, db: Session = Depends(get_db)):
    service = ShopService(db)
    shop = service.create(body)
    return {"data": AdminShopResponse.model_validate(shop).model_dump(mode="json")}


# Chi tiết shop theo ID
@router.get("/{shop_id}")
def get_shop(shop_id: str, db: Session = Depends(get_db)):
    uid = parse_uuid(shop_id, "shop")
    service = ShopService(db)
    shop = service.get(uid)
    return {"data": AdminShopResponse.model_validate(shop).model_dump(mode="json")}


# Cập nhật shop — chỉ gửi các field cần thay đổi
@router.patch("/{shop_id}")
def update_shop(shop_id: str, body: ShopUpdate, db: Session = Depends(get_db)):
    uid = parse_uuid(shop_id, "shop")
    service = ShopService(db)
    shop = service.update(uid, body)
    return {"data": AdminShopResponse.model_validate(shop).model_dump(mode="json")}
