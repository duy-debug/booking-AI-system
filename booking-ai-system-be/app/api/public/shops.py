# Public — Shops & Courses (danh sách công khai, không cần auth)

from fastapi import APIRouter, Depends, Query
from app.core.exceptions import AppError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, parse_uuid
from app.api.schemas.course import CourseResponse
from app.api.schemas.shop import ShopBrief, ShopResponse
from app.db.models.course import Course
from app.db.models.shop import Shop

router = APIRouter(prefix="/api/shops", tags=["public-shops"])


@router.get("")
def list_shops(
    is_active: bool | None = Query(None),
    db: Session = Depends(get_db),
):
    # Danh sách shop — mặc định chỉ trả shop đang hoạt động
    stmt = select(Shop)
    if is_active is not None:
        stmt = stmt.where(Shop.is_active == is_active)
    else:
        stmt = stmt.where(Shop.is_active == True)
    shops = db.scalars(stmt.order_by(Shop.name)).all()
    result = []
    for s in shops:
        item = ShopResponse.model_validate(s).model_dump(mode="json")
        item["links"] = {
            "self": f"/api/shops/{s.shop_id}",
            "courses": f"/api/shops/{s.shop_id}/courses",
            "available_slots": f"/api/shops/{s.shop_id}/available-slots",
        }
        result.append(item)
    return {"data": result, "meta": {"total": len(result)}}


@router.get("/{shop_id}")
def get_shop(shop_id: str, db: Session = Depends(get_db)):
    # Chi tiết shop
    uid = parse_uuid(shop_id, "shop")
    shop = db.get(Shop, uid)
    if not shop:
        raise AppError(404, code="SHOP_NOT_FOUND", detail="Không tìm thấy shop")
    return {"data": ShopResponse.model_validate(shop).model_dump(mode="json")}


@router.get("/{shop_id}/courses")
def list_courses(
    shop_id: str,
    course_type: str | None = Query(None),
    is_active: bool | None = Query(None),
    db: Session = Depends(get_db),
):
    # Danh sách course của shop — filter course_type, is_active
    uid = parse_uuid(shop_id, "shop")
    shop = db.get(Shop, uid)
    if not shop:
        raise AppError(404, code="SHOP_NOT_FOUND", detail="Không tìm thấy shop")

    stmt = select(Course).where(Course.shop_id == uid)
    if course_type is not None:
        stmt = stmt.where(Course.course_type == course_type)
    if is_active is not None:
        stmt = stmt.where(Course.is_active == is_active)
    else:
        stmt = stmt.where(Course.is_active == True)
    courses = db.scalars(stmt.order_by(Course.name)).all()
    return {"data": [CourseResponse.model_validate(c).model_dump(mode="json") for c in courses]}
