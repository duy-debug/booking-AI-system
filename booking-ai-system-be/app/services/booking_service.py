from datetime import date, datetime, time, timedelta
from random import SystemRandom
from uuid import UUID

# Command service cho nghiệp vụ tạo, cập nhật, hủy và tái cân bằng therapist của booking.
# Service sở hữu transaction; mọi thao tác dữ liệu được ủy quyền cho repository.
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.db.models.booking import Booking
from app.db.models.customer import Customer
from app.db.models.reservation import Reservation
from app.db.models.reservation_course import ReservationCourse
from app.repositories import (
    BookingRepository,
    ShopRepository,
    CourseRepository,
    CustomerRepository,
    ReservationRepository,
    ShiftRepository,
    TherapistRepository,
)
from app.schemas.booking import (
    BookingCreate,
    BookingPatchInput,
)
from app.mappers.booking_mapper import booking_to_detail
from app.services.booking_time import validate_booking_start
from app.services.therapist_availability_service import TherapistAvailabilityService


_secure_random = SystemRandom()


# Cộng số phút vào một thời điểm và tự quay vòng sang ngày mới nếu vượt quá 24 giờ.
def _add_minutes_to_time(t: time, minutes: int) -> time:
    total = t.hour * 60 + t.minute + minutes
    return time((total // 60) % 24, total % 60)


# Chuyển Booking cùng customer, reservation và course snapshot thành cấu trúc response chi tiết.
def _booking_to_detail(booking: Booking) -> dict:
    return booking_to_detail(booking)


class BookingService:
    # Khởi tạo với session và repository
    def __init__(self, session: Session):
        self.session = session
        self.booking_repo = BookingRepository(session)
        self.shop_repo = ShopRepository(session)
        self.course_repo = CourseRepository(session)
        self.customer_repo = CustomerRepository(session)
        self.reservation_repo = ReservationRepository(session)
        self.shift_repo = ShiftRepository(session)
        self.therapist_repo = TherapistRepository(session)
        self.availability_service = TherapistAvailabilityService(session)

    # ── Tạo booking mới ──────────────────────────────────────────────
    def create(self, body: BookingCreate, idempotency_key: str) -> dict:
        try:
            result = self._create(body, idempotency_key)
            self.session.commit()
            return result
        except Exception:
            self.session.rollback()
            raise

    # Kiểm tra toàn bộ quy tắc tạo lịch, phân công therapist và lưu booking trong transaction hiện tại.
    def _create(self, body: BookingCreate, idempotency_key: str) -> dict:
        if (
            body.number_of_people > 1
            and body.therapist_request
            and body.therapist_request.type == "specific"
        ):
            raise AppError(
                422,
                code="GROUP_BOOKING_CANNOT_REQUEST_SPECIFIC_THERAPIST",
                detail="Booking nhóm không thể chỉ định một therapist cụ thể.",
            )

        shop = self.shop_repo.find_by_id(body.shop_id)
        if not shop:
            raise AppError(404, code="SHOP_NOT_FOUND", detail="Không tìm thấy shop")
        if not shop.is_active:
            raise AppError(422, code="SHOP_INACTIVE", detail="Shop không hoạt động")

        # booking_date/start_time là giá trị local của shop trong DB. Ghép chúng với
        # timezone shop rồi so sánh ở UTC trước mọi kiểm tra availability khác.
        validate_booking_start(body.booking_date, body.start_time)

        # Kiểm tra idempotency key trùng
        existing = self.booking_repo.find_by_idempotency_key(idempotency_key)
        if existing:
            raise AppError(409, code="IDEMPOTENCY_CONFLICT",
                           detail="Idempotency-Key đã tồn tại")

        # Tìm hoặc tạo customer
        customer = self.customer_repo.find_by_phone(body.customer.phone)
        if not customer:
            customer = self.customer_repo.save(Customer(
                phone=body.customer.phone,
                name=body.customer.name,
            ))
        elif body.customer.name and customer.name != body.customer.name:
            customer.name = body.customer.name
            self.customer_repo.save(customer)

        # Validate courses + tính tổng thời lượng
        main_course = None
        total_duration = 0
        for c in body.courses:
            course = self.course_repo.find_by_id(c.course_id)
            if not course or course.shop_id != body.shop_id:
                raise AppError(404, code="COURSE_NOT_FOUND",
                               detail=f"Không tìm thấy course {c.course_id}")
            if c.course_role == "main":
                if main_course:
                    raise AppError(422, code="INVALID_COURSE_COMBO",
                                   detail="Chỉ được một course chính")
                if course.course_type != "main":
                    raise AppError(422, code="INVALID_COURSE_COMBO",
                                   detail=f"{c.course_id} không phải course type 'main'")
                main_course = course
            elif c.course_role == "addon":
                if course.course_type != "addon":
                    raise AppError(422, code="INVALID_COURSE_COMBO",
                                   detail=f"{c.course_id} không phải course type 'addon'")
            total_duration += course.duration_minutes
        if not main_course:
            raise AppError(422, code="INVALID_COURSE_COMBO", detail="Thiếu course chính")

        # Tính end_time
        end_time = _add_minutes_to_time(body.start_time, total_duration)

        # Xác định therapist cho mỗi người
        is_specific_request = bool(
            body.therapist_request
            and body.therapist_request.type == "specific"
        )
        if is_specific_request:
            therapist_ids = [self._resolve_specific_therapist_with_priority(
                shop_id=body.shop_id,
                booking_date=body.booking_date,
                start_time=body.start_time,
                end_time=end_time,
                requested_therapist_id=body.therapist_request.therapist_id,
                break_minutes=shop.therapist_break_minutes,
            )]
        else:
            therapist_ids = self._resolve_therapists(
                shop_id=body.shop_id,
                booking_date=body.booking_date,
                start_time=body.start_time,
                end_time=end_time,
                number_of_people=body.number_of_people,
                therapist_request=body.therapist_request,
            )

        # Tạo booking
        booking = Booking(
            shop_id=body.shop_id,
            customer_id=customer.customer_id,
            booking_date=body.booking_date,
            start_time=body.start_time,
            end_time=end_time,
            number_of_people=body.number_of_people,
            total_duration_minutes=total_duration,
            status="confirmed",
            therapist_request_type=body.therapist_request.type if body.therapist_request else "none",
            requested_therapist_id=(
                body.therapist_request.therapist_id
                if body.therapist_request and body.therapist_request.type == "specific"
                else None
            ),
            requested_gender=(
                body.therapist_request.gender
                if body.therapist_request and body.therapist_request.type == "gender"
                else None
            ),
            idempotency_key=idempotency_key,
        )
        self.booking_repo.save(booking)

        # Tạo reservation cho mỗi người
        if len(therapist_ids) != len(set(therapist_ids)):
            raise AppError(
                422,
                code="DUPLICATE_THERAPIST_ASSIGNMENT",
                detail="Mỗi người trong booking nhóm phải có therapist khác nhau.",
            )
        for i, tid in enumerate(therapist_ids):
            reservation = Reservation(
                booking_id=booking.booking_id,
                person_index=i + 1,
                therapist_id=tid,
                start_time=body.start_time,
                end_time=end_time,
                status="assigned",
                assignment_source="specific" if is_specific_request else "auto",
            )
            self.reservation_repo.save(reservation)

            # Tạo snapshot course cho mỗi reservation
            for c in body.courses:
                course = self.course_repo.find_by_id(c.course_id)
                snap = ReservationCourse(
                    reservation_id=reservation.reservation_id,
                    course_id=c.course_id,
                    course_role=c.course_role,
                    course_name_snapshot=course.name,
                    duration_snapshot=course.duration_minutes,
                    price_snapshot=course.price,
                )
                self.reservation_repo.save_course(snap)

        self.booking_repo.save(booking)
        return _booking_to_detail(booking)

    # ── Cập nhật booking ──────────────────────────────────────────────
    def update(self, booking_id: UUID, body: BookingPatchInput) -> dict:
        try:
            result = self._update(booking_id, body)
            self.session.commit()
            return result
        except Exception:
            self.session.rollback()
            raise

    # Điều phối cập nhật hoặc hủy booking, sau đó chuyển sang luồng cập nhật nhóm khi payload có reservations.
    def _update(self, booking_id: UUID, body: BookingPatchInput) -> dict:
        booking = self.booking_repo.find_by_id(booking_id)
        if not booking:
            raise AppError(404, code="BOOKING_NOT_FOUND", detail="Không tìm thấy booking")

        # Huỷ booking
        if body.status == "cancelled":
            booking.status = "cancelled"
            booking.cancel_reason = body.cancel_reason
            booking.cancelled_at = datetime.now()
            self.booking_repo.save(booking)
            return _booking_to_detail(booking)

        if getattr(body, "reservations", None) is not None:
            return self._update_group(booking, body)

        # Thay đổi ngày/giờ
        if body.booking_date is not None:
            booking.booking_date = body.booking_date
        if body.start_time is not None:
            booking.start_time = body.start_time
            # Tính lại end_time từ courses snapshot
            duration = booking.total_duration_minutes
            if not duration and booking.reservations:
                duration = sum(
                    rc.duration_snapshot
                    for rc in booking.reservations[0].reservation_courses
                )
            booking.end_time = _add_minutes_to_time(body.start_time, duration)
            for reservation in booking.reservations:
                reservation.start_time = body.start_time
                reservation.end_time = booking.end_time

        self.booking_repo.save(booking)
        return _booking_to_detail(booking)

    # Cập nhật toàn bộ booking nhóm theo reservation_id và đồng bộ customer, course, therapist lẫn thời gian.
    def _update_group(self, booking: Booking, body: BookingPatchInput) -> dict:
        booking_date = body.booking_date or booking.booking_date
        start_time = body.start_time or booking.start_time
        time_changed = booking_date != booking.booking_date or start_time != booking.start_time
        if time_changed:
            validate_booking_start(booking_date, start_time)

        items = body.reservations or []
        person_indexes = [item.person_index for item in items]
        if sorted(person_indexes) != list(range(1, len(items) + 1)):
            raise AppError(
                422,
                code="INVALID_PERSON_INDEXES",
                detail="person_index phải liên tục từ 1 đến số người.",
            )

        course_signatures = [
            frozenset((course.course_id, course.course_role) for course in item.courses)
            for item in items
        ]
        if len(items) > 1 and any(
            signature != course_signatures[0] for signature in course_signatures[1:]
        ):
            raise AppError(
                422,
                code="GROUP_COURSES_MUST_MATCH",
                detail="Course chính và course thêm phải giống nhau cho mọi người trong booking nhóm.",
            )

        changes_group_size = (
            len(items) > 1 and booking.number_of_people != len(items)
        )
        if changes_group_size and not body.auto_assign_therapists:
            raise AppError(
                422,
                code="GROUP_BOOKING_REQUIRES_AUTO_ASSIGNMENT",
                detail="Khi thay đổi số người của booking nhóm, therapist phải được tự động phân công.",
            )
        if body.auto_assign_therapists and not changes_group_size:
            raise AppError(
                422,
                code="AUTO_ASSIGN_NOT_ALLOWED",
                detail="Tự động phân công chỉ dùng khi thay đổi số người của booking nhóm.",
            )

        if body.auto_assign_therapists:
            if any(item.therapist_id is not None for item in items):
                raise AppError(
                    422,
                    code="GROUP_BOOKING_CANNOT_SPECIFY_THERAPIST",
                    detail="Không được chỉ định therapist khi thay đổi số người của booking nhóm.",
                )
            assigned_ids = self._auto_assign_group_therapists(
                booking, items, booking_date, start_time
            )
            for item, therapist_id in zip(
                sorted(items, key=lambda value: value.person_index), assigned_ids
            ):
                item.therapist_id = therapist_id
        elif any(item.therapist_id is None for item in items):
            raise AppError(
                422,
                code="THERAPIST_REQUIRED",
                detail="Mỗi người phải có therapist.",
            )

        therapist_ids = [item.therapist_id for item in items]
        if len(therapist_ids) != len(set(therapist_ids)):
            raise AppError(
                422,
                code="DUPLICATE_THERAPIST_ASSIGNMENT",
                detail="Mỗi người trong booking nhóm phải có therapist khác nhau.",
            )

        existing = {
            reservation.reservation_id: reservation
            for reservation in booking.reservations
        }
        supplied_ids = [
            item.reservation_id for item in items if item.reservation_id is not None
        ]
        if len(supplied_ids) != len(set(supplied_ids)):
            raise AppError(
                422,
                code="DUPLICATE_RESERVATION_ID",
                detail="reservation_id bị lặp trong payload.",
            )
        if any(reservation_id not in existing for reservation_id in supplied_ids):
            raise AppError(
                422,
                code="RESERVATION_NOT_IN_BOOKING",
                detail="Reservation không thuộc booking đang cập nhật.",
            )

        if len(items) > 1 and not body.auto_assign_therapists:
            changes_group_therapist = any(
                item.reservation_id is None
                or item.therapist_id
                != existing[item.reservation_id].therapist_id
                for item in items
            )
            if changes_group_therapist:
                raise AppError(
                    422,
                    code="GROUP_BOOKING_CANNOT_CHANGE_THERAPIST",
                    detail="Booking nhóm không được chỉ định hoặc thay đổi therapist thủ công.",
                )

        if body.customer is not None:
            customer = self.customer_repo.find_by_phone(body.customer.phone)
            if customer is None:
                customer = self.customer_repo.save(
                    Customer(phone=body.customer.phone, name=body.customer.name)
                )
            elif body.customer.name is not None:
                customer.name = body.customer.name
            booking.customer_id = customer.customer_id
            booking.customer = customer

        prepared = []
        for item in items:
            current_reservation = existing.get(item.reservation_id) if item.reservation_id else None
            therapist = self.therapist_repo.find_by_id(item.therapist_id)
            if not therapist or therapist.shop_id != booking.shop_id:
                raise AppError(
                    404,
                    code="THERAPIST_NOT_FOUND",
                    detail=f"Không tìm thấy therapist {item.therapist_id} trong shop.",
                )
            therapist_changed = (
                current_reservation is None
                or current_reservation.therapist_id != item.therapist_id
            )
            requested_courses = {
                (course.course_id, course.course_role) for course in item.courses
            }
            current_courses = {
                (course.course_id, course.course_role)
                for course in current_reservation.reservation_courses
            } if current_reservation is not None else set()
            courses_changed = current_reservation is None or requested_courses != current_courses
            schedule_changed = time_changed or therapist_changed or courses_changed

            if schedule_changed and not therapist.is_active:
                raise AppError(
                    422,
                    code="THERAPIST_INACTIVE",
                    detail=f"Therapist {therapist.name} không hoạt động.",
                )

            if courses_changed:
                course_rows, duration = self._prepare_reservation_courses(
                    booking.shop_id, item.courses
                )
            else:
                course_rows = None
                duration = sum(
                    course.duration_snapshot
                    for course in current_reservation.reservation_courses
                )
            end_time = _add_minutes_to_time(start_time, duration)
            if schedule_changed:
                active_shifts = self.shift_repo.find_by_shop(
                    booking.shop_id,
                    work_date=booking_date,
                    therapist_id=item.therapist_id,
                    is_active=True,
                )
                if not any(
                    shift.start_time <= start_time and shift.end_time >= end_time
                    for shift in active_shifts
                ):
                    raise AppError(
                        422,
                        code="OUTSIDE_SHIFT",
                        detail=f"Ca làm của therapist {therapist.name} không bao phủ khung giờ.",
                    )
                if self.shift_repo.exists_inactive_overlap(
                    item.therapist_id, booking_date, start_time, end_time
                ):
                    raise AppError(
                        422,
                        code="THERAPIST_NOT_AVAILABLE",
                        detail=f"Therapist {therapist.name} bị chặn trong khung giờ.",
                    )
                if self.reservation_repo.exists_overlap(
                    item.therapist_id,
                    booking_date,
                    start_time,
                    end_time,
                    exclude_booking_id=booking.booking_id,
                    break_minutes=getattr(
                        getattr(booking, "shop", None),
                        "therapist_break_minutes",
                        0,
                    ),
                ):
                    raise AppError(
                        409,
                        code="SLOT_CONFLICT",
                        detail=f"Therapist {therapist.name} đã có booking trong khung giờ.",
                    )
            prepared.append((item, course_rows, duration, end_time, therapist_changed))

        kept_ids = set(supplied_ids)
        for reservation_id, reservation in list(existing.items()):
            if reservation_id not in kept_ids:
                booking.reservations.remove(reservation)
                self.reservation_repo.delete(reservation)

        durations = []
        for item, course_rows, duration, end_time, therapist_changed in prepared:
            reservation = existing.get(item.reservation_id) if item.reservation_id else None
            if reservation is None:
                reservation = Reservation(
                    booking=booking,
                    person_index=item.person_index,
                    therapist_id=item.therapist_id,
                    start_time=start_time,
                    end_time=end_time,
                    status="assigned",
                    assignment_source=(
                        "auto" if body.auto_assign_therapists else "specific"
                    ),
                )
                self.reservation_repo.save(reservation)
            else:
                reservation.person_index = item.person_index
                reservation.therapist_id = item.therapist_id
                reservation.start_time = start_time
                reservation.end_time = end_time
                reservation.status = "assigned"
                if body.auto_assign_therapists:
                    reservation.assignment_source = "auto"
                elif therapist_changed:
                    reservation.assignment_source = "specific"
                if course_rows is not None:
                    reservation.reservation_courses.clear()

            if course_rows is not None:
                for course, course_role in course_rows:
                    reservation.reservation_courses.append(
                        ReservationCourse(
                            reservation_id=reservation.reservation_id,
                            course_id=course.course_id,
                            course_role=course_role,
                            course_name_snapshot=course.name,
                            duration_snapshot=course.duration_minutes,
                            price_snapshot=course.price,
                        )
                    )
            durations.append(duration)

        booking.booking_date = booking_date
        booking.start_time = start_time
        booking.number_of_people = len(items)
        booking.total_duration_minutes = max(durations)
        booking.end_time = _add_minutes_to_time(start_time, booking.total_duration_minutes)
        booking.therapist_request_type = "specific" if len(items) == 1 else "none"
        booking.requested_therapist_id = items[0].therapist_id if len(items) == 1 else None
        booking.requested_gender = None
        self.booking_repo.save(booking)
        booking.reservations.sort(key=lambda reservation: reservation.person_index)
        return _booking_to_detail(booking)

    # Chọn ngẫu nhiên đủ therapist đang rảnh cho booking nhóm và loại trừ chính booking được chỉnh sửa.
    def _auto_assign_group_therapists(
        self,
        booking: Booking,
        items: list,
        booking_date: date,
        start_time: time,
    ) -> list[UUID]:
        _, group_duration = self._prepare_reservation_courses(
            booking.shop_id, items[0].courses
        )
        group_end_time = _add_minutes_to_time(start_time, group_duration)
        availability = self.availability_service.evaluate(
            shop_id=booking.shop_id,
            booking_date=booking_date,
            start_time=start_time,
            end_time=group_end_time,
            request_type="none",
            lock_shifts=True,
            exclude_booking_id=booking.booking_id,
        )
        if availability.available_therapist_count < len(items):
            raise AppError(
                422,
                code="INSUFFICIENT_AVAILABLE_THERAPISTS",
                detail=f"Cần {len(items)} therapist nhưng chỉ có {availability.available_therapist_count} therapist khả dụng.",
            )
        selected = _secure_random.sample(
            availability.available_therapists, k=len(items)
        )
        return [therapist.therapist_id for therapist in selected]

    # Kiểm tra tổ hợp course của một người, trả các model hợp lệ và tổng thời lượng thực hiện.
    def _prepare_reservation_courses(self, shop_id: UUID, course_inputs: list) -> tuple[list, int]:
        rows = []
        duration = 0
        main_count = 0
        seen = set()
        for item in course_inputs:
            if item.course_id in seen:
                raise AppError(
                    422,
                    code="INVALID_COURSE_COMBO",
                    detail="Course bị chọn lặp cho cùng một người.",
                )
            seen.add(item.course_id)
            course = self.course_repo.find_by_id(item.course_id)
            if not course or course.shop_id != shop_id:
                raise AppError(
                    404,
                    code="COURSE_NOT_FOUND",
                    detail=f"Không tìm thấy course {item.course_id} trong shop.",
                )
            if not course.is_active:
                raise AppError(
                    422,
                    code="COURSE_INACTIVE",
                    detail=f"Course {course.name} không hoạt động.",
                )
            if item.course_role != course.course_type:
                raise AppError(
                    422,
                    code="INVALID_COURSE_COMBO",
                    detail=f"Vai trò của course {course.name} không hợp lệ.",
                )
            main_count += int(item.course_role == "main")
            duration += course.duration_minutes
            rows.append((course, item.course_role))
        if main_count != 1:
            raise AppError(
                422,
                code="INVALID_COURSE_COMBO",
                detail="Mỗi người phải có đúng một course chính.",
            )
        return rows, duration

    # ── Internal: chọn therapist ──────────────────────────────────────
    # Ưu tiên therapist được khách chỉ định bằng cách tái phân công reservation auto đang giữ therapist đó.
    def _resolve_specific_therapist_with_priority(
        self,
        shop_id: UUID,
        booking_date: date,
        start_time: time,
        end_time: time,
        requested_therapist_id: UUID,
        break_minutes: int = 0,
    ) -> UUID:
        requested = self.availability_service.evaluate(
            shop_id=shop_id,
            booking_date=booking_date,
            start_time=start_time,
            end_time=end_time,
            request_type="specific",
            requested_therapist_id=requested_therapist_id,
            lock_shifts=True,
        )
        if requested.available_therapist_count == 1:
            return requested_therapist_id
        if requested.covering_therapist_count == 0 or requested.blocked_therapist_count:
            raise AppError(
                422,
                code="THERAPIST_NOT_AVAILABLE",
                detail="Therapist được chỉ định không khả dụng trong khung giờ.",
            )

        overlap_args = (
            {"break_minutes": break_minutes} if break_minutes else {}
        )
        overlaps = self.reservation_repo.find_overlaps_for_update(
            requested_therapist_id,
            booking_date,
            start_time,
            end_time,
            **overlap_args,
        )
        if len(overlaps) != 1:
            raise AppError(
                409,
                code="THERAPIST_NOT_AVAILABLE",
                detail="Therapist được chỉ định đã có booking không thể tái cân bằng.",
            )

        displaced = overlaps[0]
        displaced_booking = displaced.booking
        if displaced.assignment_source != "auto":
            raise AppError(
                409,
                code="THERAPIST_NOT_AVAILABLE",
                detail="Therapist đang phục vụ một reservation được chỉ định và không thể thay đổi tự động.",
            )

        replacement = self.availability_service.evaluate(
            shop_id=displaced_booking.shop_id,
            booking_date=displaced_booking.booking_date,
            start_time=displaced.start_time,
            end_time=displaced.end_time,
            request_type=(
                "gender"
                if displaced_booking.therapist_request_type == "gender"
                else "none"
            ),
            requested_gender=displaced_booking.requested_gender,
            lock_shifts=True,
        )
        candidates = [
            therapist
            for therapist in replacement.available_therapists
            if therapist.therapist_id != requested_therapist_id
        ]
        if not candidates:
            raise AppError(
                409,
                code="NO_REPLACEMENT_THERAPIST_AVAILABLE",
                detail="Không có therapist khác khả dụng để thay thế cho reservation tự động.",
            )

        displaced.therapist_id = _secure_random.choice(candidates).therapist_id
        self.reservation_repo.save(displaced)
        return requested_therapist_id

    # Tìm đủ therapist theo yêu cầu none, gender hoặc specific và từ chối khi số lượng không đáp ứng.
    def _resolve_therapists(
        self,
        shop_id: UUID,
        booking_date: date,
        start_time: time,
        end_time: time,
        number_of_people: int,
        therapist_request=None,
    ) -> list[UUID]:
        request_type = therapist_request.type if therapist_request else "none"
        if number_of_people > 1 and request_type == "specific":
            raise AppError(
                422,
                code="GROUP_BOOKING_CANNOT_REQUEST_SPECIFIC_THERAPIST",
                detail="Booking nhóm không thể chỉ định một therapist cụ thể.",
            )
        result = self.availability_service.evaluate(
            shop_id=shop_id,
            booking_date=booking_date,
            start_time=start_time,
            end_time=end_time,
            request_type=request_type,
            requested_therapist_id=(
                therapist_request.therapist_id if therapist_request else None
            ),
            requested_gender=(therapist_request.gender if therapist_request else None),
            lock_shifts=True,
        )
        if result.available_therapist_count < number_of_people:
            if number_of_people > 1:
                raise AppError(
                    422,
                    code="INSUFFICIENT_AVAILABLE_THERAPISTS",
                    detail=(
                        "Không đủ therapist rảnh đồng thời cho nhóm "
                        f"{number_of_people} người."
                    ),
                )
            raise AppError(
                422,
                code="THERAPIST_NOT_AVAILABLE",
                detail="Không có therapist khả dụng trong khung giờ.",
            )
        therapist_ids = [
            therapist.therapist_id
            for therapist in result.available_therapists[:number_of_people]
        ]
        if len(therapist_ids) != len(set(therapist_ids)):
            raise AppError(
                422,
                code="DUPLICATE_THERAPIST_ASSIGNMENT",
                detail="Mỗi người trong booking nhóm phải có therapist khác nhau.",
            )
        return therapist_ids
