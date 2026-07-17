# Repository cho Course — CRUD + kiểm tra pos_course_code duy nhất trong shop
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.course import Course


class CourseRepository:
    # Khởi tạo với session database
    def __init__(self, session: Session):
        self.session = session

    # Tìm course theo ID
    def find_by_id(self, course_id: UUID) -> Course | None:
        return self.session.get(Course, course_id)

    # Danh sách course trong shop — lọc theo loại course và trạng thái
    def find_by_shop(
        self,
        shop_id: UUID,
        course_type: str | None = None,
        is_active: bool | None = None,
    ) -> list[Course]:
        stmt = select(Course).where(Course.shop_id == shop_id)
        if course_type is not None:
            stmt = stmt.where(Course.course_type == course_type)
        if is_active is not None:
            stmt = stmt.where(Course.is_active == is_active)
        stmt = stmt.order_by(Course.name)
        return list(self.session.scalars(stmt).all())

    # Tìm nhiều course theo danh sách ID, chỉ trong một shop
    def find_by_ids_and_shop(self, course_ids: list[UUID], shop_id: UUID) -> list[Course]:
        stmt = select(Course).where(
            Course.course_id.in_(course_ids),
            Course.shop_id == shop_id,
        )
        return list(self.session.scalars(stmt).all())

    # Kiểm tra pos_course_code đã tồn tại trong shop chưa
    def exists_by_pos_code_in_shop(self, pos_code: str, shop_id: UUID) -> bool:
        stmt = (
            select(Course.course_id)
            .where(Course.shop_id == shop_id, Course.pos_course_code == pos_code)
            .limit(1)
        )
        return self.session.scalar(stmt) is not None

    # Lưu course mới — add + flush
    def save(self, course: Course) -> Course:
        self.session.add(course)
        self.session.flush()
        return course
