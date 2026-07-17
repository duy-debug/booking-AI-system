from uuid import UUID

# Service cho Course — tạo, sửa, xem danh sách course trong shop; kiểm tra shop tồn tại
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.db.models.course import Course
from app.repositories.course_repository import CourseRepository
from app.repositories.shop_repository import ShopRepository
from app.schemas.course import CourseCreate, CourseUpdate


class CourseService:
    # Khởi tạo với session và repository
    def __init__(self, session: Session):
        self.session = session
        self.repo = CourseRepository(session)
        self.shop_repo = ShopRepository(session)

    # Danh sách course trong shop — kiểm tra shop tồn tại, lọc theo loại và trạng thái
    def list(self, shop_id: UUID, course_type: str | None = None, is_active: bool | None = None) -> list[Course]:
        if not self.shop_repo.find_by_id(shop_id):
            raise AppError(404, code="SHOP_NOT_FOUND", detail="Không tìm thấy shop")
        return self.repo.find_by_shop(shop_id, course_type=course_type, is_active=is_active)

    # Chi tiết course theo ID — báo lỗi 404 nếu không tìm thấy
    def get(self, course_id: UUID) -> Course:
        course = self.repo.find_by_id(course_id)
        if not course:
            raise AppError(404, code="COURSE_NOT_FOUND", detail="Không tìm thấy course")
        return course

    # Tạo course mới trong shop — kiểm tra pos_course_code duy nhất
    def create(self, shop_id: UUID, body: CourseCreate) -> Course:
        try:
            if not self.shop_repo.find_by_id(shop_id):
                raise AppError(404, code="SHOP_NOT_FOUND", detail="Không tìm thấy shop")

            if self.repo.exists_by_pos_code_in_shop(body.pos_course_code, shop_id):
                raise AppError(409, code="POS_COURSE_CODE_ALREADY_EXISTS", detail="pos_course_code đã tồn tại trong shop")

            course = Course(shop_id=shop_id, **body.model_dump())
            self.repo.save(course)
            self.session.commit()
            self.session.refresh(course)
            return course
        except Exception:
            self.session.rollback()
            raise

    # Cập nhật course — chỉ ghi các trường được gửi lên
    def update(self, course_id: UUID, body: CourseUpdate) -> Course:
        try:
            course = self.repo.find_by_id(course_id)
            if not course:
                raise AppError(404, code="COURSE_NOT_FOUND", detail="Không tìm thấy course")

            update_data = body.model_dump(exclude_unset=True)
            if "name" in update_data:
                course.name = body.name
            if "duration_minutes" in update_data:
                course.duration_minutes = body.duration_minutes
            if "price" in update_data:
                course.price = body.price
            if "course_type" in update_data:
                course.course_type = body.course_type
            if "is_active" in update_data:
                course.is_active = body.is_active

            self.session.commit()
            self.session.refresh(course)
            return course
        except Exception:
            self.session.rollback()
            raise
