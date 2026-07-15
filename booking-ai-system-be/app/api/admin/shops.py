# Admin CRUD — Shops (cửa hàng massage)

from fastapi import APIRouter, Depends, Query
from app.core.exceptions import AppError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, parse_uuid
from app.api.schemas.shop import ShopCreate, ShopResponse, ShopUpdate
from app.db.models.shop import Shop

router = APIRouter(prefix="/api/admin/shops", tags=["admin-shops"])


@router.get("")
def list_shops(
    is_active: bool | None = Query(None),
    db: Session = Depends(get_db),
):
    # Danh sách shop — filter theo is_active
    stmt = select(Shop)
    if is_active is not None:
        stmt = stmt.where(Shop.is_active == is_active)
    shops = db.scalars(stmt.order_by(Shop.shop_code)).all()
    return {
        "data": [ShopResponse.model_validate(s).model_dump(mode="json") for s in shops],
        "meta": {"total": len(shops)},
    }


@router.post("", status_code=201)
def create_shop(body: ShopCreate, db: Session = Depends(get_db)):
    # Tạo shop mới
    # Check trùng shop_code
    exist = db.scalar(select(Shop).where(Shop.shop_code == body.shop_code))
    if exist:
        raise AppError(409, code="SHOP_CODE_ALREADY_EXISTS", detail="shop_code đã tồn tại")
    # Check trùng pos_shop_code
    exist = db.scalar(select(Shop).where(Shop.pos_shop_code == body.pos_shop_code))
    if exist:
        raise AppError(409, code="POS_SHOP_CODE_ALREADY_EXISTS", detail="pos_shop_code đã tồn tại")

    shop = Shop(**body.model_dump())
    db.add(shop)
    db.commit()
    db.refresh(shop)
    return {"data": ShopResponse.model_validate(shop).model_dump(mode="json")}


@router.get("/{shop_id}")
def get_shop(shop_id: str, db: Session = Depends(get_db)):
    # Chi tiết shop
    uid = parse_uuid(shop_id, "shop")
    shop = db.get(Shop, uid)
    if not shop:
        raise AppError(404, code="SHOP_NOT_FOUND", detail="Không tìm thấy shop")
    return {"data": ShopResponse.model_validate(shop).model_dump(mode="json")}


@router.patch("/{shop_id}")
def update_shop(shop_id: str, body: ShopUpdate, db: Session = Depends(get_db)):
    # Cập nhật shop (partial update)
    uid = parse_uuid(shop_id, "shop")
    shop = db.get(Shop, uid)
    if not shop:
        raise AppError(404, code="SHOP_NOT_FOUND", detail="Không tìm thấy shop")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(shop, field, value)
    db.commit()
    db.refresh(shop)
    return {"data": ShopResponse.model_validate(shop).model_dump(mode="json")}
