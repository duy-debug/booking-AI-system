import uuid
from datetime import date, datetime, time, timedelta, timezone

# Service cho Booking — tạo, huỷ, cập nhật booking; xử lý idempotency, NG list, validation course/therapist
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.db.models.booking import Booking
from app.db.models.customer import Customer
from app.db.models.reservation import Reservation
from app.db.models.reservation_course import ReservationCourse
from app.repositories import (
    BookingRepository,
    CustomerRepository,
    ShopRepository,
    RestrictionRepository,
    CourseRepository,
    TherapistRepository,
    ReservationRepository,
)
from app.schemas.booking import (
    BookingCreate,
    BookingPatchInput,
    ReservationCourseResponse,
)


class BookingService:
    # Khởi tạo với session và các repository
    def __init__(self, session: Session):
        self.session = session
        self.booking_repo = BookingRepository(session)
        self.shop_repo = ShopRepository(session)
        self.restriction_repo = RestrictionRepository(session)
        self.course_repo = CourseRepository(session)
        self.therapist_repo = TherapistRepository(session)
        self.reservation_repo = ReservationRepository(session)
        self.customer_repo = CustomerRepository(session)

    # Tạo booking mới — idempotency, NG list, course validation, therapist gán tự động, slot conflict
    def create(self, body: BookingCreate, idempotency_key: str) -> dict:
        try:
            ik = self._parse_idempotency_key(idempotency_key)
            self._check_idempotency(ik)
            shop = self._find_shop(body.shop_id)
            self._check_shop_active(shop)
            self._check_restriction(body.customer.phone)
            total_duration, db_course_map = self._validate_courses(body)
            therapist_request_type, requested_therapist_id, requested_gender = (
                self._validate_therapist_request(body, shop.shop_id)
            )
            end_time = self._compute_end_time(body.booking_date, body.start_time, total_duration)
            self._check_slot_conflict(shop.shop_id, body.booking_date, body.start_time, end_time)
            customer = self._find_or_create_customer(body)

            booking = Booking(
                shop_id=body.shop_id,
                customer_id=customer.customer_id,
                booking_date=body.booking_date,
                start_time=body.start_time,
                end_time=end_time,
                number_of_people=body.number_of_people,
                total_duration_minutes=total_duration,
                status="confirmed",
                therapist_request_type=therapist_request_type,
                requested_therapist_id=requested_therapist_id if therapist_request_type == "specific" else None,
                requested_gender=requested_gender if therapist_request_type in ("specific", "gender") else None,
                idempotency_key=ik,
            )
            self.booking_repo.save(booking)

            if body.number_of_people == 1:
                self._create_single_reservation(booking, body, db_course_map, therapist_request_type, requested_therapist_id)
            else:
                self._create_group_reservations(booking, body, db_course_map, end_time)

            self.session.commit()
            self.session.refresh(booking)
            return self._load_booking_response(booking.booking_id)
        except Exception:
            self.session.rollback()
            raise

    # Huỷ booking — kiểm tra đã cancelled chưa, ghi lý do và thời gian huỷ
    def cancel(self, booking_id: uuid.UUID, cancel_reason: str | None = None) -> dict:
        try:
            booking = self.booking_repo.find_by_id(booking_id)
            if not booking:
                raise AppError(404, code="BOOKING_NOT_FOUND", detail="Không tìm thấy booking")
            if booking.status == "cancelled":
                raise AppError(409, code="BOOKING_ALREADY_CANCELLED", detail="Booking đã bị hủy")
            booking.status = "cancelled"
            booking.cancel_reason = cancel_reason
            booking.cancelled_at = datetime.now(timezone.utc)
            self.session.commit()
            self.session.refresh(booking)
            return self._load_booking_response(booking.booking_id)
        except Exception:
            self.session.rollback()
            raise

    # Cập nhật booking — chỉ cho phép sửa booking_date, start_time; nếu status=cancelled thì delegate sang cancel
    def update(self, booking_id: uuid.UUID, body: BookingPatchInput) -> dict:
        try:
            booking = self.booking_repo.find_by_id(booking_id)
            if not booking:
                raise AppError(404, code="BOOKING_NOT_FOUND", detail="Không tìm thấy booking")

            if body.status == "cancelled":
                return self.cancel(booking_id, body.cancel_reason)

            data = body.model_dump(exclude_unset=True, exclude_none=True)
            allowed_fields = {"booking_date", "start_time"}
            for field, value in data.items():
                if field in allowed_fields:
                    setattr(booking, field, value)

            self.session.commit()
            self.session.refresh(booking)
            return self._load_booking_response(booking.booking_id)
        except Exception:
            self.session.rollback()
            raise

    # Chi tiết booking kèm danh sách reservation và course — báo lỗi 404 nếu không tìm thấy
    def get(self, booking_id: uuid.UUID) -> dict:
        booking = self.booking_repo.find_by_id(booking_id)
        if not booking:
            raise AppError(404, code="BOOKING_NOT_FOUND", detail="Không tìm thấy booking")
        return self._load_booking_response(booking_id)

    # Nạp response đầy đủ của booking — gồm reservations và courses
    def _load_booking_response(self, booking_id: uuid.UUID) -> dict:
        booking = self.booking_repo.find_by_id(booking_id)
        if not booking:
            raise AppError(404, code="BOOKING_NOT_FOUND", detail="Không tìm thấy booking")

        reservations = self.reservation_repo.find_by_booking(booking_id)
        res_list = []
        for res in reservations:
            courses = self.reservation_repo.find_courses_by_reservation(res.reservation_id)
            res_list.append({
                "reservation_id": res.reservation_id,
                "person_index": res.person_index,
                "therapist_id": res.therapist_id,
                "start_time": res.start_time.isoformat(),
                "end_time": res.end_time.isoformat(),
                "status": res.status,
                "courses": [
                    ReservationCourseResponse.model_validate(c).model_dump(mode="json")
                    for c in courses
                ],
            })

        return {
            "booking_id": booking.booking_id,
            "shop_id": booking.shop_id,
            "customer_id": booking.customer_id,
            "booking_date": booking.booking_date.isoformat(),
            "start_time": booking.start_time.isoformat(),
            "end_time": booking.end_time.isoformat(),
            "number_of_people": booking.number_of_people,
            "total_duration_minutes": booking.total_duration_minutes,
            "status": booking.status,
            "therapist_request_type": booking.therapist_request_type,
            "requested_therapist_id": booking.requested_therapist_id,
            "requested_gender": booking.requested_gender,
            "cancel_reason": booking.cancel_reason,
            "cancelled_at": booking.cancelled_at.isoformat() if booking.cancelled_at else None,
            "created_at": booking.created_at.isoformat(),
            "updated_at": booking.updated_at.isoformat(),
            "reservations": res_list,
        }

    # Parse Idempotency-Key từ string sang UUID — báo lỗi nếu sai format
    def _parse_idempotency_key(self, key: str) -> uuid.UUID:
        try:
            return uuid.UUID(key)
        except ValueError:
            raise AppError(400, code="MISSING_IDEMPOTENCY_KEY", detail="Idempotency-Key không đúng format UUID")

    # Kiểm tra idempotency key đã tồn tại chưa (tránh tạo trùng booking)
    def _check_idempotency(self, ik: uuid.UUID) -> None:
        exist = self.booking_repo.find_by_idempotency_key(ik)
        if exist:
            raise AppError(409, code="SLOT_CONFLICT", detail="Idempotency-Key đã tồn tại")

    # Tìm shop theo ID — báo lỗi 404 nếu không tìm thấy
    def _find_shop(self, shop_id: uuid.UUID):
        shop = self.shop_repo.find_by_id(shop_id)
        if not shop:
            raise AppError(404, code="SHOP_NOT_FOUND", detail="Không tìm thấy shop")
        return shop

    # Kiểm tra shop đang hoạt động
    def _check_shop_active(self, shop) -> None:
        if not shop.is_active:
            raise AppError(422, code="SHOP_INACTIVE", detail="Shop không hoạt động")

    # Kiểm tra số điện thoại có trong NG list không
    def _check_restriction(self, phone: str) -> None:
        restriction = self.restriction_repo.find_active_by_phone(phone)
        if restriction:
            raise AppError(403, code="CUSTOMER_IN_NG_LIST", detail="Số điện thoại không được phép đặt booking")

    # Kiểm tra course hợp lệ — main/addon, không trùng main, có ít nhất 1 main
    def _validate_courses(self, body: BookingCreate) -> tuple[int, dict]:
        total_duration = 0
        has_main = False
        course_ids = [c.course_id for c in body.courses]
        db_courses = self.course_repo.find_by_ids_and_shop(course_ids, body.shop_id)
        db_course_map = {c.course_id: c for c in db_courses}
        for c in body.courses:
            course = db_course_map.get(c.course_id)
            if not course:
                raise AppError(404, code="COURSE_NOT_FOUND", detail=f"Không tìm thấy course {c.course_id}")
            if c.course_role == "main":
                if has_main:
                    raise AppError(422, code="INVALID_COURSE_COMBO", detail="Chỉ được chọn 1 main course")
                has_main = True
                if course.course_type != "main":
                    raise AppError(422, code="INVALID_COURSE_COMBO", detail=f"Course {c.course_id} không phải main type")
            elif c.course_role == "addon":
                if course.course_type != "addon":
                    raise AppError(422, code="INVALID_COURSE_COMBO", detail=f"Course {c.course_id} không phải addon type")
            total_duration += course.duration_minutes
        if not has_main:
            raise AppError(422, code="ADDON_REQUIRES_MAIN_COURSE", detail="Cần ít nhất 1 main course")
        return total_duration, db_course_map

    # Kiểm tra yêu cầu therapist — specific/gender/none, không cho phép với booking nhóm
    def _validate_therapist_request(self, body: BookingCreate, shop_id: uuid.UUID) -> tuple[str, uuid.UUID | None, str | None]:
        therapist_request = body.therapist_request
        requested_therapist_id = None
        requested_gender = None
        therapist_request_type = "none"

        if therapist_request:
            if body.number_of_people > 1 and therapist_request.type != "none":
                raise AppError(422, code="GROUP_BOOKING_CANNOT_REQUEST_THERAPIST", detail="Booking nhóm không được yêu cầu therapist")
            if therapist_request.type == "specific":
                if not therapist_request.therapist_id:
                    raise AppError(422, code="INVALID_THERAPIST_DATA", detail="Cần therapist_id khi type = specific")
                therapist = self.therapist_repo.find_by_id(therapist_request.therapist_id)
                if not therapist or therapist.shop_id != shop_id:
                    raise AppError(404, code="THERAPIST_NOT_FOUND", detail="Không tìm thấy therapist")
                requested_therapist_id = therapist.therapist_id
                requested_gender = therapist.gender
            elif therapist_request.type == "gender":
                if not therapist_request.gender:
                    raise AppError(422, code="INVALID_THERAPIST_DATA", detail="Cần gender khi type = gender")
                requested_gender = therapist_request.gender
            therapist_request_type = therapist_request.type

        return therapist_request_type, requested_therapist_id, requested_gender

    # Tính giờ kết thúc dựa trên start_time + tổng thời lượng course
    def _compute_end_time(self, booking_date: date, start_time: time, total_duration: int) -> time:
        from datetime import datetime
        start_dt = datetime.combine(booking_date, start_time)
        end_dt = start_dt + timedelta(minutes=total_duration)
        return end_dt.time()

    # Kiểm tra slot đã có người đặt chưa (xung đột reservation)
    def _check_slot_conflict(self, shop_id: uuid.UUID, booking_date: date, start_time: time, end_time: time) -> None:
        conflict = self.reservation_repo.exists_slot_conflict(shop_id, booking_date, start_time, end_time)
        if conflict:
            raise AppError(409, code="SLOT_CONFLICT", detail="Slot đã có người đặt")

    # Tìm customer theo phone — nếu chưa có thì tạo mới; cập nhật tên nếu đã có
    def _find_or_create_customer(self, body: BookingCreate) -> Customer:
        customer = self.customer_repo.find_by_phone(body.customer.phone)
        if not customer:
            customer = Customer(
                phone=body.customer.phone,
                name=body.customer.name,
            )
            self.customer_repo.save(customer)
        elif body.customer.name:
            customer.name = body.customer.name
        return customer

    # Tạo reservation cho booking 1 người — gán therapist theo yêu cầu hoặc active đầu tiên
    def _create_single_reservation(
        self,
        booking: Booking,
        body: BookingCreate,
        db_course_map: dict,
        therapist_request_type: str,
        requested_therapist_id: uuid.UUID | None,
    ) -> None:
        res_therapist_id = None
        if therapist_request_type == "specific" and requested_therapist_id:
            res_therapist_id = requested_therapist_id
        else:
            therapists = self.therapist_repo.find_active_by_shop(body.shop_id, limit=1)
            first_therapist = therapists[0] if therapists else None
            res_therapist_id = first_therapist.therapist_id if first_therapist else None

        if not res_therapist_id:
            raise AppError(422, code="THERAPIST_NOT_AVAILABLE", detail="Không có therapist khả dụng")

        reservation = Reservation(
            booking_id=booking.booking_id,
            person_index=1,
            therapist_id=res_therapist_id,
            start_time=body.start_time,
            end_time=booking.end_time,
            status="assigned",
        )
        self.reservation_repo.save(reservation)

        for c in body.courses:
            course = db_course_map[c.course_id]
            rc = ReservationCourse(
                reservation_id=reservation.reservation_id,
                course_id=c.course_id,
                course_role=c.course_role,
                duration_snapshot=course.duration_minutes,
                price_snapshot=course.price,
                course_name_snapshot=course.name,
            )
            self.session.add(rc)

    # Tạo reservation cho booking nhóm — gán therapist theo số người, mỗi người một therapist
    def _create_group_reservations(
        self,
        booking: Booking,
        body: BookingCreate,
        db_course_map: dict,
        end_time: time,
    ) -> None:
        available_therapists = self.therapist_repo.find_active_by_shop(body.shop_id, limit=body.number_of_people)
        if len(available_therapists) < body.number_of_people:
            raise AppError(422, code="THERAPIST_NOT_AVAILABLE", detail="Không đủ therapist cho booking nhóm")

        for i in range(body.number_of_people):
            tid = available_therapists[i].therapist_id
            res = Reservation(
                booking_id=booking.booking_id,
                person_index=i + 1,
                therapist_id=tid,
                start_time=body.start_time,
                end_time=end_time,
                status="assigned",
            )
            self.reservation_repo.save(res)

            for c in body.courses:
                course = db_course_map[c.course_id]
                rc = ReservationCourse(
                    reservation_id=res.reservation_id,
                    course_id=c.course_id,
                    course_role=c.course_role,
                    duration_snapshot=course.duration_minutes,
                    price_snapshot=course.price,
                    course_name_snapshot=course.name,
                )
                self.session.add(rc)
