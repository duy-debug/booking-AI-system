from datetime import date, time
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.repositories import (
    ShopRepository,
    CourseRepository,
    RestrictionRepository,
    TherapistRepository,
    ShiftRepository,
    BookingRepository,
    ReservationRepository,
    CustomerRepository,
)


@pytest.fixture(scope="module")
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="module")
def booking_data(client: TestClient, test_data: dict):
    """Create a booking + reservation for Phase 3B repo tests."""
    idem_key = str(uuid.uuid4())
    r = client.post(
        "/api/bookings",
        json={
            "shop_id": test_data["shop_id"],
            "booking_date": "2026-07-20",
            "start_time": "14:00",
            "number_of_people": 1,
            "customer": {"phone": test_data["phone"], "name": "Test Customer"},
            "courses": [{"course_id": test_data["course_id"], "course_role": "main"}],
            "therapist_request": {"type": "specific", "therapist_id": test_data["therapist_id"], "gender": None},
            "confirmed_by_customer": True,
        },
        headers={"Idempotency-Key": idem_key},
    )
    assert r.status_code == 201, f"Create booking fail: {r.text}"
    d = r.json()["data"]
    return {
        "booking_id": d["booking_id"],
        "reservation_id": d["reservations"][0]["reservation_id"],
        "idem_key": idem_key,
    }


class TestShopRepository:

    def test_find_all_active(self, db: Session):
        repo = ShopRepository(db)
        all_active = repo.find_all(is_active=True)
        assert len(all_active) > 0
        for s in all_active:
            assert s.is_active is True

    def test_find_all_no_filter(self, db: Session):
        repo = ShopRepository(db)
        all_shops = repo.find_all()
        assert len(all_shops) > 0

    def test_exists_by_code(self, db: Session, test_data: dict):
        repo = ShopRepository(db)
        shop = repo.find_by_id(uuid.UUID(test_data["shop_id"]))
        assert shop is not None
        assert repo.exists_by_code(shop.shop_code) is True

    def test_exists_by_code_not_found(self, db: Session):
        repo = ShopRepository(db)
        assert repo.exists_by_code("non-existent-code-xyz") is False

    def test_exists_by_pos_code(self, db: Session, test_data: dict):
        repo = ShopRepository(db)
        shop = repo.find_by_id(uuid.UUID(test_data["shop_id"]))
        assert shop is not None
        assert repo.exists_by_pos_code(shop.pos_shop_code) is True

    def test_find_by_id(self, db: Session, test_data: dict):
        repo = ShopRepository(db)
        shop = repo.find_by_id(uuid.UUID(test_data["shop_id"]))
        assert shop is not None
        assert str(shop.shop_id) == test_data["shop_id"]


class TestCourseRepository:

    def test_find_by_shop_with_type_filter(self, db: Session, test_data: dict):
        repo = CourseRepository(db)
        shop_id = uuid.UUID(test_data["shop_id"])
        courses = repo.find_by_shop(shop_id, course_type="main")
        assert len(courses) > 0
        for c in courses:
            assert c.course_type == "main"

    def test_exists_by_pos_code_in_shop(self, db: Session, test_data: dict):
        repo = CourseRepository(db)
        course = repo.find_by_id(uuid.UUID(test_data["course_id"]))
        assert course is not None
        shop_id = uuid.UUID(test_data["shop_id"])
        assert repo.exists_by_pos_code_in_shop(course.pos_course_code, shop_id) is True

    def test_exists_by_pos_code_in_shop_not_found(self, db: Session, test_data: dict):
        repo = CourseRepository(db)
        shop_id = uuid.UUID(test_data["shop_id"])
        assert repo.exists_by_pos_code_in_shop("non-existent-code", shop_id) is False

    def test_find_by_id(self, db: Session, test_data: dict):
        repo = CourseRepository(db)
        course = repo.find_by_id(uuid.UUID(test_data["course_id"]))
        assert course is not None
        assert str(course.course_id) == test_data["course_id"]

    def test_find_by_shop_inactive_filter(self, db: Session, test_data: dict):
        repo = CourseRepository(db)
        shop_id = uuid.UUID(test_data["shop_id"])
        courses = repo.find_by_shop(shop_id, is_active=False)
        assert len(courses) == 0

    def test_find_by_ids_and_shop(self, db: Session, test_data: dict):
        repo = CourseRepository(db)
        shop_id = uuid.UUID(test_data["shop_id"])
        course_id = uuid.UUID(test_data["course_id"])
        courses = repo.find_by_ids_and_shop([course_id], shop_id)
        assert len(courses) == 1
        assert courses[0].course_id == course_id


class TestRestrictionRepository:

    def test_find_active_by_phone_not_found(self, db: Session):
        repo = RestrictionRepository(db)
        r = repo.find_active_by_phone("0000000000")
        assert r is None

    def test_find_all_with_phone_filter(self, db: Session, test_data: dict):
        repo = RestrictionRepository(db)
        restrictions = repo.find_all(phone=test_data["phone"])
        assert isinstance(restrictions, list)

    def test_find_all_with_is_active(self, db: Session):
        repo = RestrictionRepository(db)
        restrictions = repo.find_all(is_active=True)
        assert isinstance(restrictions, list)


class TestTherapistRepository:

    def test_find_by_id(self, db: Session, test_data: dict):
        repo = TherapistRepository(db)
        therapist = repo.find_by_id(uuid.UUID(test_data["therapist_id"]))
        assert therapist is not None
        assert str(therapist.therapist_id) == test_data["therapist_id"]

    def test_find_by_id_not_found(self, db: Session):
        repo = TherapistRepository(db)
        assert repo.find_by_id(uuid.uuid4()) is None

    def test_find_by_shop(self, db: Session, test_data: dict):
        repo = TherapistRepository(db)
        shop_id = uuid.UUID(test_data["shop_id"])
        therapists = repo.find_by_shop(shop_id)
        assert len(therapists) > 0
        assert all(t.shop_id == shop_id for t in therapists)

    def test_find_active_by_shop(self, db: Session, test_data: dict):
        repo = TherapistRepository(db)
        shop_id = uuid.UUID(test_data["shop_id"])
        therapists = repo.find_active_by_shop(shop_id)
        assert len(therapists) > 0
        assert all(t.is_active for t in therapists)

    def test_exists_by_pos_code_in_shop(self, db: Session, test_data: dict):
        repo = TherapistRepository(db)
        therapist = repo.find_by_id(uuid.UUID(test_data["therapist_id"]))
        assert therapist is not None
        shop_id = uuid.UUID(test_data["shop_id"])
        assert repo.exists_by_pos_code_in_shop(therapist.pos_therapist_code, shop_id) is True

    def test_exists_by_pos_code_in_shop_not_found(self, db: Session, test_data: dict):
        repo = TherapistRepository(db)
        shop_id = uuid.UUID(test_data["shop_id"])
        assert repo.exists_by_pos_code_in_shop("non-existent-code", shop_id) is False


class TestShiftRepository:

    def test_find_by_id(self, db: Session, test_data: dict):
        repo = ShiftRepository(db)
        shift = repo.find_by_id(uuid.UUID(test_data["shift_id"]))
        assert shift is not None
        assert str(shift.shift_id) == test_data["shift_id"]

    def test_find_by_id_not_found(self, db: Session):
        repo = ShiftRepository(db)
        assert repo.find_by_id(uuid.uuid4()) is None

    def test_find_by_shop(self, db: Session, test_data: dict):
        repo = ShiftRepository(db)
        shop_id = uuid.UUID(test_data["shop_id"])
        shifts = repo.find_by_shop(shop_id)
        assert len(shifts) > 0
        assert all(s.shop_id == shop_id for s in shifts)

    def test_find_by_therapist_and_date(self, db: Session, test_data: dict):
        repo = ShiftRepository(db)
        tid = uuid.UUID(test_data["therapist_id"])
        shift = repo.find_by_therapist_and_date(tid, date(2026, 7, 20))
        assert shift is not None

    def test_find_by_therapist_and_date_not_found(self, db: Session, test_data: dict):
        repo = ShiftRepository(db)
        tid = uuid.UUID(test_data["therapist_id"])
        shift = repo.find_by_therapist_and_date(tid, date(2026, 7, 19))
        assert shift is None

    def test_exists_conflict(self, db: Session, test_data: dict):
        repo = ShiftRepository(db)
        shift = repo.find_by_id(uuid.UUID(test_data["shift_id"]))
        assert shift is not None
        tid = uuid.UUID(test_data["therapist_id"])
        assert repo.exists_conflict(tid, shift.work_date, shift.start_time, shift.end_time) is True

    def test_exists_conflict_not_found(self, db: Session, test_data: dict):
        repo = ShiftRepository(db)
        tid = uuid.UUID(test_data["therapist_id"])
        assert repo.exists_conflict(tid, date(2026, 7, 19), time(9, 0), time(18, 0)) is False

    def test_find_available_with_therapist(self, db: Session, test_data: dict):
        repo = ShiftRepository(db)
        shop_id = uuid.UUID(test_data["shop_id"])
        shifts = repo.find_available_with_therapist(shop_id, date(2026, 7, 20))
        assert len(shifts) > 0
        for s in shifts:
            assert s.is_active is True
            assert s.therapist is not None


class TestBookingRepository:

    def test_find_by_id(self, db: Session, test_data: dict, booking_data: dict):
        repo = BookingRepository(db)
        booking = repo.find_by_id(uuid.UUID(booking_data["booking_id"]))
        assert booking is not None
        assert str(booking.booking_id) == booking_data["booking_id"]

    def test_find_by_id_not_found(self, db: Session):
        repo = BookingRepository(db)
        assert repo.find_by_id(uuid.uuid4()) is None

    def test_find_by_idempotency_key(self, db: Session, booking_data: dict):
        repo = BookingRepository(db)
        booking = repo.find_by_idempotency_key(booking_data["idem_key"])
        assert booking is not None

    def test_find_by_idempotency_key_not_found(self, db: Session):
        repo = BookingRepository(db)
        assert repo.find_by_idempotency_key(str(uuid.uuid4())) is None

    def test_find_public_all_by_phone(self, db: Session, test_data: dict, booking_data: dict):
        repo = BookingRepository(db)
        bookings = repo.find_public_all(phone=test_data["phone"])
        assert len(bookings) > 0
        assert any(str(b.booking_id) == booking_data["booking_id"] for b in bookings)


class TestReservationRepository:

    def test_find_by_booking(self, db: Session, booking_data: dict):
        repo = ReservationRepository(db)
        reservations = repo.find_by_booking(uuid.UUID(booking_data["booking_id"]))
        assert len(reservations) > 0
        assert str(reservations[0].reservation_id) == booking_data["reservation_id"]

    def test_find_by_therapist_and_date(self, db: Session, test_data: dict, booking_data: dict):
        repo = ReservationRepository(db)
        tid = uuid.UUID(test_data["therapist_id"])
        reservations = repo.find_by_therapist_and_date(tid, date(2026, 7, 20))
        assert len(reservations) > 0

    def test_find_courses_by_reservation(self, db: Session, booking_data: dict):
        repo = ReservationRepository(db)
        courses = repo.find_courses_by_reservation(uuid.UUID(booking_data["reservation_id"]))
        assert len(courses) > 0

    def test_exists_slot_conflict(self, db: Session, test_data: dict):
        repo = ReservationRepository(db)
        shop_id = uuid.UUID(test_data["shop_id"])
        assert repo.exists_slot_conflict(shop_id, date(2026, 7, 20), time(13, 0), time(15, 0)) is True

    def test_exists_overlap(self, db: Session, test_data: dict):
        repo = ReservationRepository(db)
        tid = uuid.UUID(test_data["therapist_id"])
        assert repo.exists_overlap(tid, date(2026, 7, 20), time(13, 0), time(15, 0)) is True


class TestCustomerRepository:

    def test_find_by_phone(self, db: Session, test_data: dict):
        repo = CustomerRepository(db)
        customer = repo.find_by_phone(test_data["phone"])
        assert customer is not None
        assert customer.phone == test_data["phone"]

    def test_find_by_phone_not_found(self, db: Session):
        repo = CustomerRepository(db)
        assert repo.find_by_phone("0000000000") is None

    def test_find_by_id(self, db: Session, test_data: dict):
        repo = CustomerRepository(db)
        customer = repo.find_by_phone(test_data["phone"])
        assert customer is not None
        found = repo.find_by_id(customer.customer_id)
        assert found is not None
        assert found.customer_id == customer.customer_id
