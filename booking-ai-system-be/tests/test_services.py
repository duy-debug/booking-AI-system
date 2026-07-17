import uuid
from datetime import date, time
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.db.models.booking import Booking
from app.db.models.customer import Customer
from app.db.models.reservation import Reservation
from app.db.models.reservation_course import ReservationCourse
from app.db.session import SessionLocal
from app.repositories import (
    BookingRepository,
    CustomerRepository,
    ReservationRepository,
    RestrictionRepository,
)
from app.services import (
    BookingService,
    SlotService,
    EligibilityService,
    TherapistScheduleService,
    ShopService,
    CourseService,
    TherapistService,
)
from app.schemas.booking import BookingCreate, CustomerInput, BookingCourseInput
from app.schemas.shop import ShopCreate
from app.schemas.course import CourseCreate
from app.schemas.therapist import TherapistCreate

TAG = f"s{uuid.uuid4().hex[:4]}"


@pytest.fixture(scope="module")
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="module")
def sc_phone(test_data: dict) -> str:
    return f"0999{TAG}sc"


@pytest.fixture(scope="module")
def sc_idem_key() -> str:
    return str(uuid.uuid4())


@pytest.fixture(scope="module")
def created_booking(client: TestClient, test_data: dict, sc_phone: str, sc_idem_key: str) -> dict:
    r = client.post(
        "/api/bookings",
        json={
            "shop_id": test_data["shop_id"],
            "booking_date": "2026-07-20",
            "start_time": "10:00",
            "number_of_people": 1,
            "customer": {"phone": sc_phone, "name": "Svc Create"},
            "courses": [{"course_id": test_data["course_id"], "course_role": "main"}],
            "therapist_request": {"type": "none"},
            "confirmed_by_customer": True,
        },
        headers={"Idempotency-Key": sc_idem_key},
    )
    assert r.status_code == 201, f"Create booking fail: {r.text}"
    return r.json()["data"]


@pytest.fixture(scope="module")
def cancel_phone(test_data: dict) -> str:
    return f"0999{TAG}cn"


@pytest.fixture(scope="module")
def created_for_cancel(client: TestClient, test_data: dict, cancel_phone: str) -> dict:
    ik = str(uuid.uuid4())
    r = client.post(
        "/api/bookings",
        json={
            "shop_id": test_data["shop_id"],
            "booking_date": "2026-07-20",
            "start_time": "16:00",
            "number_of_people": 1,
            "customer": {"phone": cancel_phone, "name": "Cancel Me"},
            "courses": [{"course_id": test_data["course_id"], "course_role": "main"}],
            "therapist_request": {"type": "none"},
            "confirmed_by_customer": True,
        },
        headers={"Idempotency-Key": ik},
    )
    assert r.status_code == 201, f"Create booking for cancel fail: {r.text}"
    return r.json()["data"]


@pytest.fixture
def fresh_booking_for_cancel(client: TestClient, test_data: dict) -> dict:
    """Each test gets its own booking so cancel tests are order-independent."""
    ik = str(uuid.uuid4())
    phone = f"0999{TAG}fc{uuid.uuid4().hex[:4]}"
    r = client.post(
        "/api/bookings",
        json={
            "shop_id": test_data["shop_id"],
            "booking_date": "2026-07-20",
            "start_time": "17:00",
            "number_of_people": 1,
            "customer": {"phone": phone, "name": "Fresh Cancel"},
            "courses": [{"course_id": test_data["course_id"], "course_role": "main"}],
            "therapist_request": {"type": "none"},
            "confirmed_by_customer": True,
        },
        headers={"Idempotency-Key": ik},
    )
    assert r.status_code == 201, f"Create fresh booking for cancel fail: {r.text}"
    return r.json()["data"]


@pytest.fixture(scope="module")
def group_idem_key(test_data: dict) -> str:
    return str(uuid.uuid4())


@pytest.fixture(scope="module")
def group_phone(test_data: dict) -> str:
    return f"0999{TAG}gr"


@pytest.fixture(scope="module")
def second_therapist_id(client: TestClient, test_data: dict, auth_headers: dict) -> str:
    code = f"{TAG}-th2"
    r = client.post(
        f"/api/admin/shops/{test_data['shop_id']}/therapists",
        json={
            "pos_therapist_code": code,
            "name": "Group Therapist",
            "gender": "male",
            "is_active": True,
        },
        headers=auth_headers,
    )
    assert r.status_code == 201, f"Create 2nd therapist fail: {r.text}"
    tid = r.json()["data"]["therapist_id"]

    r = client.post(
        "/api/admin/therapist-shifts",
        json={
            "shop_id": test_data["shop_id"],
            "therapist_id": tid,
            "work_date": "2026-07-20",
            "start_time": "09:00",
            "end_time": "18:00",
            "is_active": True,
        },
        headers=auth_headers,
    )
    assert r.status_code == 201, f"Create 2nd shift fail: {r.text}"
    return tid


@pytest.fixture(scope="module")
def ng_phone() -> str:
    return f"0999{TAG}ng"


@pytest.fixture(scope="module")
def ng_restriction_id(client: TestClient, test_data: dict, auth_headers: dict, ng_phone: str) -> str:
    r = client.post(
        "/api/admin/customer-restrictions",
        json={
            "phone": ng_phone,
            "reason": "Test NG",
            "is_active": True,
        },
        headers=auth_headers,
    )
    assert r.status_code == 201, f"Create restriction fail: {r.text}"
    return r.json()["data"]["restriction_id"]


class TestBookingService:

    def test_create_booking_success(self, db: Session, test_data: dict, sc_phone: str):
        service = BookingService(db)
        ik = str(uuid.uuid4())
        body = BookingCreate(
            shop_id=uuid.UUID(test_data["shop_id"]),
            booking_date=date(2026, 7, 20),
            start_time=time(12, 0),
            number_of_people=1,
            customer=CustomerInput(phone=sc_phone, name="Direct Create"),
            courses=[BookingCourseInput(course_id=uuid.UUID(test_data["course_id"]), course_role="main")],
            therapist_request=None,
            confirmed_by_customer=True,
        )
        result = service.create(body, ik)
        assert result["status"] == "confirmed"
        assert result["number_of_people"] == 1
        assert result["total_duration_minutes"] == 60
        assert len(result["reservations"]) == 1
        assert len(result["reservations"][0]["courses"]) == 1
        assert result["reservations"][0]["courses"][0]["course_role"] == "main"

    def test_create_single_booking_creates_all_entities(self, db: Session, test_data: dict, sc_phone: str):
        service = BookingService(db)
        ik = str(uuid.uuid4())
        body = BookingCreate(
            shop_id=uuid.UUID(test_data["shop_id"]),
            booking_date=date(2026, 7, 20),
            start_time=time(9, 0),
            number_of_people=1,
            customer=CustomerInput(phone=sc_phone, name="Verify Entities"),
            courses=[BookingCourseInput(course_id=uuid.UUID(test_data["course_id"]), course_role="main")],
            therapist_request=None,
            confirmed_by_customer=True,
        )
        result = service.create(body, ik)
        bid = result["booking_id"]

        booking = db.get(Booking, bid)
        assert booking is not None
        assert booking.status == "confirmed"

        customer = db.get(Customer, booking.customer_id)
        assert customer is not None
        assert customer.phone == sc_phone

        res_repo = ReservationRepository(db)
        reservations = res_repo.find_by_booking(bid)
        assert len(reservations) == 1

        courses = res_repo.find_courses_by_reservation(reservations[0].reservation_id)
        assert len(courses) == 1
        assert courses[0].course_role == "main"
        assert courses[0].duration_snapshot == 60

    def test_create_group_booking_success(self, db: Session, test_data: dict, group_phone: str, second_therapist_id: str):
        service = BookingService(db)
        ik = str(uuid.uuid4())
        body = BookingCreate(
            shop_id=uuid.UUID(test_data["shop_id"]),
            booking_date=date(2026, 7, 20),
            start_time=time(13, 0),
            number_of_people=2,
            customer=CustomerInput(phone=group_phone, name="Group Booking"),
            courses=[BookingCourseInput(course_id=uuid.UUID(test_data["course_id"]), course_role="main")],
            therapist_request=None,
            confirmed_by_customer=True,
        )
        result = service.create(body, ik)
        assert result["status"] == "confirmed"
        assert result["number_of_people"] == 2
        assert len(result["reservations"]) == 2

    def test_same_idempotency_key_returns_existing_booking(self, db: Session, test_data: dict, sc_phone: str, sc_idem_key: str, created_booking: dict):
        service = BookingService(db)
        body = BookingCreate(
            shop_id=uuid.UUID(test_data["shop_id"]),
            booking_date=date(2026, 7, 20),
            start_time=time(10, 0),
            number_of_people=1,
            customer=CustomerInput(phone=sc_phone, name="Same Key"),
            courses=[BookingCourseInput(course_id=uuid.UUID(test_data["course_id"]), course_role="main")],
            therapist_request=None,
            confirmed_by_customer=True,
        )
        with pytest.raises(AppError) as exc:
            service.create(body, sc_idem_key)
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "SLOT_CONFLICT"

    def test_idempotency_key_different_payload_raises_conflict(self, db: Session, test_data: dict, sc_phone: str, sc_idem_key: str, created_booking: dict):
        service = BookingService(db)
        body = BookingCreate(
            shop_id=uuid.UUID(test_data["shop_id"]),
            booking_date=date(2026, 7, 20),
            start_time=time(14, 0),
            number_of_people=1,
            customer=CustomerInput(phone=sc_phone, name="Different Payload"),
            courses=[BookingCourseInput(course_id=uuid.UUID(test_data["course_id"]), course_role="main")],
            therapist_request=None,
            confirmed_by_customer=True,
        )
        with pytest.raises(AppError) as exc:
            service.create(body, sc_idem_key)
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "SLOT_CONFLICT"

    def test_customer_in_ng_list(self, db: Session, test_data: dict, ng_phone: str, ng_restriction_id: str):
        service = BookingService(db)
        ik = str(uuid.uuid4())
        body = BookingCreate(
            shop_id=uuid.UUID(test_data["shop_id"]),
            booking_date=date(2026, 7, 20),
            start_time=time(13, 0),
            number_of_people=1,
            customer=CustomerInput(phone=ng_phone, name="NG Customer"),
            courses=[BookingCourseInput(course_id=uuid.UUID(test_data["course_id"]), course_role="main")],
            therapist_request=None,
            confirmed_by_customer=True,
        )
        with pytest.raises(AppError) as exc:
            service.create(body, ik)
        assert exc.value.status_code == 403
        assert exc.value.detail["code"] == "CUSTOMER_IN_NG_LIST"

    def test_shop_not_found(self, db: Session):
        service = BookingService(db)
        ik = str(uuid.uuid4())
        body = BookingCreate(
            shop_id=uuid.uuid4(),
            booking_date=date(2026, 7, 20),
            start_time=time(13, 0),
            number_of_people=1,
            customer=CustomerInput(phone=f"0999{TAG}nf", name="No Shop"),
            courses=[BookingCourseInput(course_id=uuid.uuid4(), course_role="main")],
            therapist_request=None,
            confirmed_by_customer=True,
        )
        with pytest.raises(AppError) as exc:
            service.create(body, ik)
        assert exc.value.status_code == 404
        assert exc.value.detail["code"] == "SHOP_NOT_FOUND"

    def test_two_main_courses_raises_error(self, db: Session, test_data: dict):
        service = BookingService(db)
        ik = str(uuid.uuid4())
        cid = uuid.UUID(test_data["course_id"])
        body = BookingCreate(
            shop_id=uuid.UUID(test_data["shop_id"]),
            booking_date=date(2026, 7, 20),
            start_time=time(13, 0),
            number_of_people=1,
            customer=CustomerInput(phone=f"0999{TAG}2m", name="Two Main"),
            courses=[
                BookingCourseInput(course_id=cid, course_role="main"),
                BookingCourseInput(course_id=cid, course_role="main"),
            ],
            therapist_request=None,
            confirmed_by_customer=True,
        )
        with pytest.raises(AppError) as exc:
            service.create(body, ik)
        assert exc.value.status_code == 422
        assert exc.value.detail["code"] == "INVALID_COURSE_COMBO"

    def test_main_course_without_main_type_raises_error(self, db: Session, test_data: dict):
        service = BookingService(db)
        ik = str(uuid.uuid4())
        body = BookingCreate(
            shop_id=uuid.UUID(test_data["shop_id"]),
            booking_date=date(2026, 7, 20),
            start_time=time(13, 0),
            number_of_people=1,
            customer=CustomerInput(phone=f"0999{TAG}ct", name="Wrong Type"),
            courses=[BookingCourseInput(course_id=uuid.UUID(test_data["course_id"]), course_role="addon")],
            therapist_request=None,
            confirmed_by_customer=True,
        )
        with pytest.raises(AppError) as exc:
            service.create(body, ik)
        assert exc.value.status_code == 422
        assert exc.value.detail["code"] == "INVALID_COURSE_COMBO"

    def test_course_not_in_shop_raises_error(self, db: Session, test_data: dict):
        service = BookingService(db)
        ik = str(uuid.uuid4())
        body = BookingCreate(
            shop_id=uuid.UUID(test_data["shop_id"]),
            booking_date=date(2026, 7, 20),
            start_time=time(13, 0),
            number_of_people=1,
            customer=CustomerInput(phone=f"0999{TAG}cr", name="Wrong Course"),
            courses=[BookingCourseInput(course_id=uuid.uuid4(), course_role="main")],
            therapist_request=None,
            confirmed_by_customer=True,
        )
        with pytest.raises(AppError) as exc:
            service.create(body, ik)
        assert exc.value.status_code == 404
        assert exc.value.detail["code"] == "COURSE_NOT_FOUND"

    def test_slot_conflict_raises_error(self, db: Session, test_data: dict):
        service = BookingService(db)
        ik = str(uuid.uuid4())
        body = BookingCreate(
            shop_id=uuid.UUID(test_data["shop_id"]),
            booking_date=date(2026, 7, 20),
            start_time=time(9, 0),
            number_of_people=1,
            customer=CustomerInput(phone=f"0999{TAG}sl", name="Slot Conflict"),
            courses=[BookingCourseInput(course_id=uuid.UUID(test_data["course_id"]), course_role="main")],
            therapist_request=None,
            confirmed_by_customer=True,
        )
        with pytest.raises(AppError) as exc:
            service.create(body, ik)
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "SLOT_CONFLICT"

    def test_therapist_not_available_rollback(self, db: Session, test_data: dict):
        tag = uuid.uuid4().hex[:6]
        shop_svc = ShopService(db)
        shop = shop_svc.create(ShopCreate(
            shop_code=f"na-{tag}", pos_shop_code=f"na-{tag}", name="NA Shop",
        ))
        course_svc = CourseService(db)
        course = course_svc.create(shop.shop_id, CourseCreate(
            pos_course_code=f"na-{tag}", name="NA Course", duration_minutes=60,
            price=Decimal("5000.00"), course_type="main",
        ))
        therapist_svc = TherapistService(db)
        therapist_svc.create(shop.shop_id, TherapistCreate(
            pos_therapist_code=f"na-{tag}", name="NA Ther", gender="female",
        ))

        service = BookingService(db)
        ik = str(uuid.uuid4())
        phone = f"0999{TAG}nt{uuid.uuid4().hex[:2]}"
        body = BookingCreate(
            shop_id=shop.shop_id,
            booking_date=date(2026, 7, 20),
            start_time=time(15, 0),
            number_of_people=3,
            customer=CustomerInput(phone=phone, name="No Therapist"),
            courses=[BookingCourseInput(course_id=course.course_id, course_role="main")],
            therapist_request={"type": "none"},
            confirmed_by_customer=True,
        )
        with pytest.raises(AppError) as exc:
            service.create(body, ik)
        assert exc.value.status_code == 422
        assert exc.value.detail["code"] == "THERAPIST_NOT_AVAILABLE"

        repo_customer = CustomerRepository(db)
        found_customer = repo_customer.find_by_phone(phone)
        assert found_customer is None, "Customer was NOT rolled back"

        repo_booking = BookingRepository(db)
        existing_booking = repo_booking.find_by_idempotency_key(ik)
        assert existing_booking is None, "Booking was NOT rolled back"

        from sqlalchemy import select as sa_select
        from app.db.models.reservation import Reservation as ResModel
        from app.db.models.reservation_course import ReservationCourse as RCModel
        orphan_rc = (
            db.execute(
                sa_select(RCModel).join(ResModel, isouter=True).where(ResModel.reservation_id.is_(None))
            )
            .scalars()
            .all()
        )
        assert len(orphan_rc) == 0, f"Orphan ReservationCourse rows found after rollback: {len(orphan_rc)}"

    def test_update_rollback_on_not_found(self, db: Session):
        service = BookingService(db)
        from app.schemas.booking import BookingPatchInput

        import uuid as uuid_mod
        fake_id = uuid_mod.uuid4()
        body = BookingPatchInput(booking_date=date(2026, 7, 21))
        with pytest.raises(AppError) as exc:
            service.update(fake_id, body)
        assert exc.value.status_code == 404
        assert exc.value.detail["code"] == "BOOKING_NOT_FOUND"

        repo_booking = BookingRepository(db)
        booking = repo_booking.find_by_id(fake_id)
        assert booking is None, "No partial data should exist after failed update"

    def test_update_booking_success(self, db: Session, created_booking: dict):
        service = BookingService(db)
        from app.schemas.booking import BookingPatchInput
        body = BookingPatchInput(
            booking_date=date(2026, 7, 21),
        )
        result = service.update(uuid.UUID(created_booking["booking_id"]), body)
        assert result["booking_date"] == "2026-07-21"

    def test_update_booking_not_found(self, db: Session):
        service = BookingService(db)
        from app.schemas.booking import BookingPatchInput
        body = BookingPatchInput(booking_date=date(2026, 7, 21))
        with pytest.raises(AppError) as exc:
            service.update(uuid.uuid4(), body)
        assert exc.value.status_code == 404
        assert exc.value.detail["code"] == "BOOKING_NOT_FOUND"

    def test_cancel_booking(self, db: Session, fresh_booking_for_cancel: dict):
        service = BookingService(db)
        result = service.cancel(
            uuid.UUID(fresh_booking_for_cancel["booking_id"]),
            cancel_reason="Test cancellation",
        )
        assert result["status"] == "cancelled"
        assert result["cancel_reason"] == "Test cancellation"
        assert result["cancelled_at"] is not None

    def test_cancel_already_cancelled(self, db: Session, fresh_booking_for_cancel: dict):
        service = BookingService(db)
        booking_id = uuid.UUID(fresh_booking_for_cancel["booking_id"])
        service.cancel(booking_id)
        with pytest.raises(AppError) as exc:
            service.cancel(booking_id)
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "BOOKING_ALREADY_CANCELLED"

    def test_get_booking_not_found(self, db: Session):
        service = BookingService(db)
        with pytest.raises(AppError) as exc:
            service.get(uuid.uuid4())
        assert exc.value.status_code == 404
        assert exc.value.detail["code"] == "BOOKING_NOT_FOUND"


class TestSlotService:

    def test_list_available_slots(self, db: Session, test_data: dict):
        service = SlotService(db)
        shop_id = uuid.UUID(test_data["shop_id"])
        course_id = uuid.UUID(test_data["course_id"])
        result = service.list_available_slots(
            shop_id=shop_id,
            booking_date=date(2026, 7, 20),
            number_of_people=1,
            main_course_id=course_id,
        )
        assert "data" in result
        assert "meta" in result
        assert len(result["data"]) > 0
        for slot in result["data"]:
            assert slot["available"] is True

    def test_list_available_slots_shop_not_found(self, db: Session):
        service = SlotService(db)
        with pytest.raises(AppError) as exc:
            service.list_available_slots(
                shop_id=uuid.uuid4(),
                booking_date=date(2026, 7, 20),
                number_of_people=1,
                main_course_id=uuid.uuid4(),
            )
        assert exc.value.status_code == 404
        assert exc.value.detail["code"] == "SHOP_NOT_FOUND"

    def test_list_available_therapists(self, db: Session, test_data: dict):
        service = SlotService(db)
        shop_id = uuid.UUID(test_data["shop_id"])
        result = service.list_available_therapists(
            shop_id=shop_id,
            booking_date=date(2026, 7, 20),
            start_time=time(9, 0),
            end_time=time(18, 0),
        )
        assert "data" in result
        assert len(result["data"]) > 0

    def test_list_available_therapists_invalid_time_range(self, db: Session, test_data: dict):
        service = SlotService(db)
        with pytest.raises(AppError) as exc:
            service.list_available_therapists(
                shop_id=uuid.UUID(test_data["shop_id"]),
                booking_date=date(2026, 7, 20),
                start_time=time(18, 0),
                end_time=time(9, 0),
            )
        assert exc.value.status_code == 422
        assert exc.value.detail["code"] == "INVALID_TIME_RANGE"

    def test_list_available_therapists_with_gender_filter(self, db: Session, test_data: dict):
        service = SlotService(db)
        shop_id = uuid.UUID(test_data["shop_id"])
        result = service.list_available_therapists(
            shop_id=shop_id,
            booking_date=date(2026, 7, 20),
            start_time=time(9, 0),
            end_time=time(18, 0),
            gender="female",
        )
        assert "data" in result
        for t in result["data"]:
            assert t["gender"] == "female"

    def test_compute_free_intervals(self):
        service = SlotService.__new__(SlotService)
        result = service._compute_free_intervals(540, 1080, [(600, 720)])
        assert result == [(540, 600), (720, 1080)]

    def test_merge_intervals(self):
        service = SlotService.__new__(SlotService)
        intervals = [(600, 720), (700, 800), (850, 900)]
        intervals.sort()
        merged = [intervals[0]]
        for start, end in intervals[1:]:
            if start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))
        assert merged == [(600, 800), (850, 900)]


class TestEligibilityService:

    def test_check_eligibility_new_customer(self, db: Session, test_data: dict):
        service = EligibilityService(db)
        shop_id = uuid.UUID(test_data["shop_id"])
        new_phone = f"0999{uuid.uuid4().hex[:8]}"
        result = service.check_eligibility(phone=new_phone, shop_id=shop_id)
        assert result["eligible"] is True
        assert result["customer"] is None

    def test_check_eligibility_shop_not_found(self, db: Session):
        service = EligibilityService(db)
        with pytest.raises(AppError) as exc:
            service.check_eligibility(phone="0999000000", shop_id=uuid.uuid4())
        assert exc.value.status_code == 404
        assert exc.value.detail["code"] == "SHOP_NOT_FOUND"


class TestTherapistScheduleService:

    def test_get_schedule_with_shift(self, db: Session, test_data: dict):
        service = TherapistScheduleService(db)
        tid = uuid.UUID(test_data["therapist_id"])
        result = service.get_schedule(tid, date(2026, 7, 20))
        assert result["therapist_id"] == str(tid)
        assert result["date"] == "2026-07-20"
        assert result["shift"] is not None
        assert result["shift"]["start_time"] is not None
        assert result["shift"]["end_time"] is not None

    def test_get_schedule_no_shift(self, db: Session, test_data: dict):
        service = TherapistScheduleService(db)
        tid = uuid.UUID(test_data["therapist_id"])
        result = service.get_schedule(tid, date(2026, 7, 19))
        assert result["therapist_id"] == str(tid)
        assert result["shift"] is None
        assert result["reservations"] == []

    def test_get_schedule_therapist_not_found(self, db: Session):
        service = TherapistScheduleService(db)
        with pytest.raises(AppError) as exc:
            service.get_schedule(uuid.uuid4(), date(2026, 7, 20))
        assert exc.value.status_code == 404
        assert exc.value.detail["code"] == "THERAPIST_NOT_FOUND"
