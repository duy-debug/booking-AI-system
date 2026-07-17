from fastapi import APIRouter, Depends, Query
from app.core.exceptions import AppError
from sqlalchemy.orm import Session

from app.api.deps import get_db, parse_uuid
from app.repositories.shop_repository import ShopRepository
from app.repositories.course_repository import CourseRepository
from app.schemas.course import PublicCourseResponse
from app.schemas.shop import PublicShopResponse

router = APIRouter(prefix="/api/shops", tags=["public-shops"])


# Danh sách shop công khai — kèm link HATEOAS
@router.get("")
def list_shops(
    is_active: bool | None = Query(None),
    db: Session = Depends(get_db),
):
    repo = ShopRepository(db)
    effective_active = is_active if is_active is not None else True
    shops = repo.find_all(is_active=effective_active, order_by="name")
    result = []
    for s in shops:
        item = PublicShopResponse.model_validate(s).model_dump(mode="json")
        item["links"] = {
            "self": f"/api/shops/{s.shop_id}",
            "courses": f"/api/shops/{s.shop_id}/courses",
            "available_slots": f"/api/shops/{s.shop_id}/available-slots",
        }
        result.append(item)
    return {"data": result, "meta": {"total": len(result)}}


# Chi tiết shop công khai
@router.get("/{shop_id}")
def get_shop(shop_id: str, db: Session = Depends(get_db)):
    uid = parse_uuid(shop_id, "shop")
    repo = ShopRepository(db)
    shop = repo.find_by_id(uid)
    if not shop:
        raise AppError(404, code="SHOP_NOT_FOUND", detail="Không tìm thấy shop")
    return {"data": PublicShopResponse.model_validate(shop).model_dump(mode="json")}


# Danh sách course công khai trong shop — lọc theo loại và trạng thái
@router.get("/{shop_id}/courses")
def list_courses(
    shop_id: str,
    course_type: str | None = Query(None),
    is_active: bool | None = Query(None),
    db: Session = Depends(get_db),
):
    uid = parse_uuid(shop_id, "shop")
    shop_repo = ShopRepository(db)
    shop = shop_repo.find_by_id(uid)
    if not shop:
        raise AppError(404, code="SHOP_NOT_FOUND", detail="Không tìm thấy shop")

    effective_active = is_active if is_active is not None else True
    course_repo = CourseRepository(db)
    courses = course_repo.find_by_shop(uid, course_type=course_type, is_active=effective_active)
    return {"data": [PublicCourseResponse.model_validate(c).model_dump(mode="json") for c in courses]}
