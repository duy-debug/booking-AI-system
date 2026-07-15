# Admin CRUD — Courses (dịch vụ massage) — nested dưới shop

from fastapi import APIRouter, Depends, Query
from app.core.exceptions import AppError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, parse_uuid
from app.api.schemas.course import CourseCreate, CourseResponse, CourseUpdate
from app.db.models.course import Course
from app.db.models.shop import Shop

router = APIRouter(prefix="/api/admin", tags=["admin-courses"])


@router.get("/shops/{shop_id}/courses")
def list_courses(
    shop_id: str,
    course_type: str | None = Query(None),
    is_active: bool | None = Query(None),
    db: Session = Depends(get_db),
):
    # Danh sách course của shop — filter theo course_type, is_active
    uid = parse_uuid(shop_id, "shop")
    shop = db.get(Shop, uid)
    if not shop:
        raise AppError(404, code="SHOP_NOT_FOUND", detail="Không tìm thấy shop")

    stmt = select(Course).where(Course.shop_id == uid)
    if course_type is not None:
        stmt = stmt.where(Course.course_type == course_type)
    if is_active is not None:
        stmt = stmt.where(Course.is_active == is_active)
    courses = db.scalars(stmt.order_by(Course.name)).all()
    return {"data": [CourseResponse.model_validate(c).model_dump(mode="json") for c in courses]}


@router.post("/shops/{shop_id}/courses", status_code=201)
def create_course(shop_id: str, body: CourseCreate, db: Session = Depends(get_db)):
    # Tạo course mới cho shop
    uid = parse_uuid(shop_id, "shop")
    shop = db.get(Shop, uid)
    if not shop:
        raise AppError(404, code="SHOP_NOT_FOUND", detail="Không tìm thấy shop")

    # Check trùng pos_course_code trong shop
    exist = db.scalar(
        select(Course).where(Course.shop_id == uid, Course.pos_course_code == body.pos_course_code)
    )
    if exist:
        raise AppError(409, code="POS_COURSE_CODE_ALREADY_EXISTS", detail="pos_course_code đã tồn tại trong shop")

    course = Course(shop_id=uid, **body.model_dump())
    db.add(course)
    db.commit()
    db.refresh(course)
    return {"data": CourseResponse.model_validate(course).model_dump(mode="json")}


@router.get("/courses/{course_id}")
def get_course(course_id: str, db: Session = Depends(get_db)):
    # Chi tiết course
    uid = parse_uuid(course_id, "course")
    course = db.get(Course, uid)
    if not course:
        raise AppError(404, code="COURSE_NOT_FOUND", detail="Không tìm thấy course")
    return {"data": CourseResponse.model_validate(course).model_dump(mode="json")}


@router.patch("/courses/{course_id}")
def update_course(course_id: str, body: CourseUpdate, db: Session = Depends(get_db)):
    # Cập nhật course (partial update)
    uid = parse_uuid(course_id, "course")
    course = db.get(Course, uid)
    if not course:
        raise AppError(404, code="COURSE_NOT_FOUND", detail="Không tìm thấy course")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(course, field, value)
    db.commit()
    db.refresh(course)
    return {"data": CourseResponse.model_validate(course).model_dump(mode="json")}
