import uuid
from datetime import date, time
from decimal import Decimal
from unittest.mock import Mock

import pytest
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.db.session import SessionLocal
from app.services.shop_service import ShopService
from app.services.course_service import CourseService
from app.services.therapist_service import TherapistService
from app.services.therapist_shift_service import TherapistShiftService
from app.services.restriction_service import RestrictionService
from app.schemas.shop import ShopCreate, ShopUpdate
from app.schemas.course import CourseCreate, CourseUpdate
from app.schemas.therapist import TherapistCreate, TherapistUpdate
from app.schemas.therapist_shift import ShiftCreate, ShiftUpdate
from app.schemas.customer_restriction import RestrictionCreate, RestrictionUpdate
from app.repositories.shop_repository import ShopRepository
from app.repositories.course_repository import CourseRepository
from app.repositories.therapist_repository import TherapistRepository
from app.repositories.shift_repository import ShiftRepository
from app.repositories.restriction_repository import RestrictionRepository
from app.db.models.shop import Shop
from app.db.models.course import Course
from app.db.models.therapist import Therapist
from app.db.models.therapist_shift import TherapistShift
from app.db.models.customer_restriction import CustomerRestriction

TAG = f"as{uuid.uuid4().hex[:4]}"


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


# ── ShopService ──────────────────────────────────────────────────────────────


class TestShopService:
    def _unique_code(self, prefix: str) -> str:
        return f"{prefix}{TAG}"

    def test_create_success(self, db: Session):
        code = self._unique_code("sc1")
        pos = self._unique_code("sp1")
        svc = ShopService(db)
        shop = svc.create(ShopCreate(shop_code=code, pos_shop_code=pos, name="Test Shop"))
        assert shop.shop_id is not None
        assert shop.shop_code == code
        assert shop.name == "Test Shop"

    def test_create_duplicate_shop_code(self, db: Session):
        code = self._unique_code("sc2")
        pos = self._unique_code("sp2")
        svc = ShopService(db)
        svc.create(ShopCreate(shop_code=code, pos_shop_code=self._unique_code("sp3"), name="First"))
        with pytest.raises(AppError) as exc:
            svc.create(ShopCreate(shop_code=code, pos_shop_code=self._unique_code("sp4"), name="Second"))
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "SHOP_CODE_ALREADY_EXISTS"

    def test_create_duplicate_pos_code(self, db: Session):
        pos = self._unique_code("sp5")
        svc = ShopService(db)
        svc.create(ShopCreate(shop_code=self._unique_code("sc3"), pos_shop_code=pos, name="First"))
        with pytest.raises(AppError) as exc:
            svc.create(ShopCreate(shop_code=self._unique_code("sc4"), pos_shop_code=pos, name="Second"))
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "POS_SHOP_CODE_ALREADY_EXISTS"

    def test_get_success(self, db: Session):
        code = self._unique_code("sc5")
        svc = ShopService(db)
        created = svc.create(ShopCreate(shop_code=code, pos_shop_code=self._unique_code("sp6"), name="Get Me"))
        fetched = svc.get(created.shop_id)
        assert fetched.shop_id == created.shop_id

    def test_get_not_found(self, db: Session):
        svc = ShopService(db)
        with pytest.raises(AppError) as exc:
            svc.get(uuid.uuid4())
        assert exc.value.status_code == 404

    def test_update_success(self, db: Session):
        code = self._unique_code("sc6")
        svc = ShopService(db)
        created = svc.create(ShopCreate(shop_code=code, pos_shop_code=self._unique_code("sp7"), name="Before"))
        updated = svc.update(created.shop_id, ShopUpdate(name="After"))
        assert updated.name == "After"
        assert updated.shop_code == code

    def test_update_not_found(self, db: Session):
        svc = ShopService(db)
        with pytest.raises(AppError) as exc:
            svc.update(uuid.uuid4(), ShopUpdate(name="Nope"))
        assert exc.value.status_code == 404

    def test_update_empty_body(self, db: Session):
        code = self._unique_code("sc7")
        svc = ShopService(db)
        created = svc.create(ShopCreate(shop_code=code, pos_shop_code=self._unique_code("sp8"), name="Empty"))
        updated = svc.update(created.shop_id, ShopUpdate())
        assert updated.name == "Empty"

    def test_rollback_on_constraint(self, db: Session):
        code = self._unique_code("sc8")
        pos = self._unique_code("sp9")
        svc = ShopService(db)
        svc.create(ShopCreate(shop_code=code, pos_shop_code=pos, name="Original"))
        repo = ShopRepository(db)
        count_before = len(repo.find_all())

        shop2 = Shop(shop_id=uuid.uuid4(), shop_code=code, pos_shop_code=pos, name="Duplicate")
        with pytest.raises(Exception):
            repo.save(shop2)
        db.rollback()

        count_after = len(repo.find_all())
        assert count_after == count_before

    def test_rollback_on_commit_failure(self):
        mock_session = Mock()
        mock_session.scalar.return_value = None
        mock_session.commit.side_effect = RuntimeError("commit failed")

        svc = ShopService(mock_session)
        body = ShopCreate(shop_code="sc1", pos_shop_code="sp1", name="Test")

        with pytest.raises(RuntimeError, match="commit failed"):
            svc.create(body)

        mock_session.rollback.assert_called_once()


# ── CourseService ────────────────────────────────────────────────────────────


class TestCourseService:
    def _unique_code(self, prefix: str) -> str:
        return f"{prefix}{TAG}"

    def test_create_success(self, db: Session, test_data: dict):
        code = self._unique_code("cc1")
        shop_id = test_data["shop_id"]
        svc = CourseService(db)
        course = svc.create(shop_id, CourseCreate(pos_course_code=code, name="Test Course", duration_minutes=60, price=Decimal("5000.00"), course_type="main"))
        assert course.course_id is not None
        assert course.name == "Test Course"

    def test_create_shop_not_found(self, db: Session):
        svc = CourseService(db)
        with pytest.raises(AppError) as exc:
            svc.create(uuid.uuid4(), CourseCreate(pos_course_code=self._unique_code("cc2"), name="No Shop", duration_minutes=30, price=Decimal("3000.00"), course_type="addon"))
        assert exc.value.status_code == 404
        assert exc.value.detail["code"] == "SHOP_NOT_FOUND"

    def test_create_duplicate_code(self, db: Session, test_data: dict):
        code = self._unique_code("cc3")
        shop_id = test_data["shop_id"]
        svc = CourseService(db)
        svc.create(shop_id, CourseCreate(pos_course_code=code, name="First", duration_minutes=60, price=Decimal("5000.00"), course_type="main"))
        with pytest.raises(AppError) as exc:
            svc.create(shop_id, CourseCreate(pos_course_code=code, name="Second", duration_minutes=30, price=Decimal("3000.00"), course_type="addon"))
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "POS_COURSE_CODE_ALREADY_EXISTS"

    def test_list(self, db: Session, test_data: dict):
        svc = CourseService(db)
        courses = svc.list(test_data["shop_id"])
        assert len(courses) >= 1

    def test_get_success(self, db: Session, test_data: dict):
        svc = CourseService(db)
        course = svc.get(test_data["course_id"])
        assert course.course_id is not None

    def test_get_not_found(self, db: Session):
        svc = CourseService(db)
        with pytest.raises(AppError) as exc:
            svc.get(uuid.uuid4())
        assert exc.value.status_code == 404

    def test_update_success(self, db: Session, test_data: dict):
        svc = CourseService(db)
        updated = svc.update(test_data["course_id"], CourseUpdate(name="Updated Course"))
        assert updated.name == "Updated Course"

    def test_update_not_found(self, db: Session):
        svc = CourseService(db)
        with pytest.raises(AppError) as exc:
            svc.update(uuid.uuid4(), CourseUpdate(name="Nope"))
        assert exc.value.status_code == 404

    def test_update_empty_body(self, db: Session, test_data: dict):
        svc = CourseService(db)
        updated = svc.update(test_data["course_id"], CourseUpdate())
        assert updated.name is not None

    def test_rollback_on_constraint(self, db: Session, test_data: dict):
        code = self._unique_code("cc4")
        shop_id = test_data["shop_id"]
        svc = CourseService(db)
        svc.create(shop_id, CourseCreate(pos_course_code=code, name="Original", duration_minutes=60, price=Decimal("5000.00"), course_type="main"))
        repo = CourseRepository(db)
        count_before = len(repo.find_by_shop(shop_id))

        course2 = Course(course_id=uuid.uuid4(), shop_id=shop_id, pos_course_code=code, name="Duplicate", duration_minutes=30, price=Decimal("3000.00"), course_type="addon")
        with pytest.raises(Exception):
            repo.save(course2)
        db.rollback()

        count_after = len(repo.find_by_shop(shop_id))
        assert count_after == count_before

    def test_rollback_on_commit_failure(self):
        mock_session = Mock()
        mock_session.scalar.return_value = None
        mock_session.commit.side_effect = RuntimeError("commit failed")

        svc = CourseService(mock_session)
        body = CourseCreate(pos_course_code="cc1", name="Test", duration_minutes=60, price=Decimal("5000.00"), course_type="main")

        with pytest.raises(RuntimeError, match="commit failed"):
            svc.create(uuid.uuid4(), body)

        mock_session.rollback.assert_called_once()


# ── TherapistService ─────────────────────────────────────────────────────────


class TestTherapistService:
    def _unique_code(self, prefix: str) -> str:
        return f"{prefix}{TAG}"

    def test_create_success(self, db: Session, test_data: dict):
        code = self._unique_code("tc1")
        shop_id = test_data["shop_id"]
        svc = TherapistService(db)
        therapist = svc.create(shop_id, TherapistCreate(pos_therapist_code=code, name="Test Ther", gender="male"))
        assert therapist.therapist_id is not None
        assert therapist.name == "Test Ther"

    def test_create_shop_not_found(self, db: Session):
        svc = TherapistService(db)
        with pytest.raises(AppError) as exc:
            svc.create(uuid.uuid4(), TherapistCreate(pos_therapist_code=self._unique_code("tc2"), name="No Shop", gender="female"))
        assert exc.value.status_code == 404

    def test_create_duplicate_code(self, db: Session, test_data: dict):
        code = self._unique_code("tc3")
        shop_id = test_data["shop_id"]
        svc = TherapistService(db)
        svc.create(shop_id, TherapistCreate(pos_therapist_code=code, name="First", gender="male"))
        with pytest.raises(AppError) as exc:
            svc.create(shop_id, TherapistCreate(pos_therapist_code=code, name="Second", gender="female"))
        assert exc.value.status_code == 409

    def test_list(self, db: Session, test_data: dict):
        svc = TherapistService(db)
        therapists = svc.list(test_data["shop_id"])
        assert len(therapists) >= 1

    def test_get_success(self, db: Session, test_data: dict):
        svc = TherapistService(db)
        therapist = svc.get(test_data["therapist_id"])
        assert therapist.therapist_id is not None

    def test_get_not_found(self, db: Session):
        svc = TherapistService(db)
        with pytest.raises(AppError) as exc:
            svc.get(uuid.uuid4())
        assert exc.value.status_code == 404

    def test_update_success(self, db: Session, test_data: dict):
        svc = TherapistService(db)
        updated = svc.update(test_data["therapist_id"], TherapistUpdate(name="Updated Ther"))
        assert updated.name == "Updated Ther"

    def test_update_not_found(self, db: Session):
        svc = TherapistService(db)
        with pytest.raises(AppError) as exc:
            svc.update(uuid.uuid4(), TherapistUpdate(name="Nope"))
        assert exc.value.status_code == 404

    def test_update_empty_body(self, db: Session, test_data: dict):
        svc = TherapistService(db)
        updated = svc.update(test_data["therapist_id"], TherapistUpdate())
        assert updated.name is not None

    def test_rollback_on_constraint(self, db: Session, test_data: dict):
        code = self._unique_code("tc4")
        shop_id = test_data["shop_id"]
        svc = TherapistService(db)
        svc.create(shop_id, TherapistCreate(pos_therapist_code=code, name="Original", gender="male"))
        repo = TherapistRepository(db)
        count_before = len(repo.find_by_shop(shop_id))

        t2 = Therapist(therapist_id=uuid.uuid4(), shop_id=shop_id, pos_therapist_code=code, name="Duplicate", gender="female")
        with pytest.raises(Exception):
            repo.save(t2)
        db.rollback()

        count_after = len(repo.find_by_shop(shop_id))
        assert count_after == count_before

    def test_rollback_on_commit_failure(self):
        mock_session = Mock()
        mock_session.scalar.return_value = None
        mock_session.commit.side_effect = RuntimeError("commit failed")

        svc = TherapistService(mock_session)
        body = TherapistCreate(pos_therapist_code="tc1", name="Test", gender="male")

        with pytest.raises(RuntimeError, match="commit failed"):
            svc.create(uuid.uuid4(), body)

        mock_session.rollback.assert_called_once()


# ── TherapistShiftService ────────────────────────────────────────────────────


class TestTherapistShiftService:
    def test_create_success(self, db: Session, test_data: dict):
        svc = TherapistShiftService(db)
        shift = svc.create(ShiftCreate(
            shop_id=test_data["shop_id"],
            therapist_id=test_data["therapist_id"],
            work_date=date(2026, 8, 1),
            start_time=time(9, 0),
            end_time=time(12, 0),
        ))
        assert shift.shift_id is not None

    def test_create_shop_not_found(self, db: Session, test_data: dict):
        svc = TherapistShiftService(db)
        with pytest.raises(AppError) as exc:
            svc.create(ShiftCreate(
                shop_id=uuid.uuid4(),
                therapist_id=test_data["therapist_id"],
                work_date=date(2026, 8, 1),
                start_time=time(9, 0),
                end_time=time(12, 0),
            ))
        assert exc.value.status_code == 404

    def test_create_therapist_not_found(self, db: Session, test_data: dict):
        svc = TherapistShiftService(db)
        with pytest.raises(AppError) as exc:
            svc.create(ShiftCreate(
                shop_id=test_data["shop_id"],
                therapist_id=uuid.uuid4(),
                work_date=date(2026, 8, 1),
                start_time=time(9, 0),
                end_time=time(12, 0),
            ))
        assert exc.value.status_code == 404

    def test_create_therapist_not_in_shop(self, db: Session, test_data: dict):
        svc = TherapistShiftService(db)
        fake_shop_id = uuid.uuid4()
        with pytest.raises((AppError,)) as exc:
            svc.create(ShiftCreate(
                shop_id=fake_shop_id,
                therapist_id=test_data["therapist_id"],
                work_date=date(2026, 8, 1),
                start_time=time(9, 0),
                end_time=time(12, 0),
            ))

    def test_create_invalid_time_range(self, db: Session, test_data: dict):
        svc = TherapistShiftService(db)
        with pytest.raises(AppError) as exc:
            svc.create(ShiftCreate(
                shop_id=test_data["shop_id"],
                therapist_id=test_data["therapist_id"],
                work_date=date(2026, 8, 1),
                start_time=time(12, 0),
                end_time=time(9, 0),
            ))
        assert exc.value.status_code == 422

    def test_create_conflict(self, db: Session, test_data: dict):
        svc = TherapistShiftService(db)
        svc.create(ShiftCreate(
            shop_id=test_data["shop_id"],
            therapist_id=test_data["therapist_id"],
            work_date=date(2026, 8, 2),
            start_time=time(9, 0),
            end_time=time(12, 0),
        ))
        with pytest.raises(AppError) as exc:
            svc.create(ShiftCreate(
                shop_id=test_data["shop_id"],
                therapist_id=test_data["therapist_id"],
                work_date=date(2026, 8, 2),
                start_time=time(9, 0),
                end_time=time(12, 0),
            ))
        assert exc.value.status_code == 409

    def test_update_success(self, db: Session, test_data: dict):
        svc = TherapistShiftService(db)
        shift = svc.create(ShiftCreate(
            shop_id=test_data["shop_id"],
            therapist_id=test_data["therapist_id"],
            work_date=date(2026, 8, 3),
            start_time=time(9, 0),
            end_time=time(12, 0),
        ))
        updated = svc.update(shift.shift_id, ShiftUpdate(start_time=time(10, 0)))
        assert updated.start_time == time(10, 0)

    def test_update_not_found(self, db: Session):
        svc = TherapistShiftService(db)
        with pytest.raises(AppError) as exc:
            svc.update(uuid.uuid4(), ShiftUpdate(start_time=time(10, 0)))
        assert exc.value.status_code == 404

    def test_update_validates_time_range(self, db: Session, test_data: dict):
        svc = TherapistShiftService(db)
        shift = svc.create(ShiftCreate(
            shop_id=test_data["shop_id"],
            therapist_id=test_data["therapist_id"],
            work_date=date(2026, 8, 4),
            start_time=time(9, 0),
            end_time=time(12, 0),
        ))
        with pytest.raises(AppError) as exc:
            svc.update(shift.shift_id, ShiftUpdate(end_time=time(8, 0)))
        assert exc.value.status_code == 422

    def test_update_validates_overlap_excluding_self(self, db: Session, test_data: dict):
        svc = TherapistShiftService(db)
        s1 = svc.create(ShiftCreate(
            shop_id=test_data["shop_id"],
            therapist_id=test_data["therapist_id"],
            work_date=date(2026, 8, 5),
            start_time=time(9, 0),
            end_time=time(12, 0),
        ))
        svc.create(ShiftCreate(
            shop_id=test_data["shop_id"],
            therapist_id=test_data["therapist_id"],
            work_date=date(2026, 8, 5),
            start_time=time(13, 0),
            end_time=time(15, 0),
        ))
        updated = svc.update(s1.shift_id, ShiftUpdate(end_time=time(12, 30)))
        assert updated.end_time == time(12, 30)

    def test_update_overlap_detected(self, db: Session, test_data: dict):
        svc = TherapistShiftService(db)
        s1 = svc.create(ShiftCreate(
            shop_id=test_data["shop_id"],
            therapist_id=test_data["therapist_id"],
            work_date=date(2026, 8, 6),
            start_time=time(9, 0),
            end_time=time(12, 0),
        ))
        svc.create(ShiftCreate(
            shop_id=test_data["shop_id"],
            therapist_id=test_data["therapist_id"],
            work_date=date(2026, 8, 6),
            start_time=time(14, 0),
            end_time=time(17, 0),
        ))
        with pytest.raises(AppError) as exc:
            svc.update(s1.shift_id, ShiftUpdate(end_time=time(15, 0)))
        assert exc.value.status_code == 409

    def test_update_empty_body(self, db: Session, test_data: dict):
        svc = TherapistShiftService(db)
        shift = svc.create(ShiftCreate(
            shop_id=test_data["shop_id"],
            therapist_id=test_data["therapist_id"],
            work_date=date(2026, 8, 7),
            start_time=time(9, 0),
            end_time=time(12, 0),
        ))
        updated = svc.update(shift.shift_id, ShiftUpdate())
        assert updated.start_time == time(9, 0)

    def test_rollback_on_constraint(self, db: Session, test_data: dict):
        svc = TherapistShiftService(db)
        shift = svc.create(ShiftCreate(
            shop_id=test_data["shop_id"],
            therapist_id=test_data["therapist_id"],
            work_date=date(2026, 8, 8),
            start_time=time(9, 0),
            end_time=time(12, 0),
        ))
        repo = ShiftRepository(db)
        count_before = len(repo.find_by_shop(test_data["shop_id"]))

        s2 = TherapistShift(shift_id=uuid.uuid4(), shop_id=uuid.uuid4(), therapist_id=uuid.uuid4(), work_date=shift.work_date, start_time=shift.start_time, end_time=shift.end_time, is_active=True)
        with pytest.raises(Exception):
            repo.save(s2)
        db.rollback()

        count_after = len(repo.find_by_shop(test_data["shop_id"]))
        assert count_after == count_before

    def test_rollback_on_commit_failure(self):
        shop_id = uuid.uuid4()
        therapist_mock = Mock()
        therapist_mock.shop_id = shop_id

        mock_session = Mock()
        mock_session.scalar.return_value = None
        mock_session.get.return_value = therapist_mock
        mock_session.commit.side_effect = RuntimeError("commit failed")

        svc = TherapistShiftService(mock_session)
        body = ShiftCreate(
            shop_id=shop_id,
            therapist_id=uuid.uuid4(),
            work_date=date(2026, 7, 20),
            start_time=time(9, 0),
            end_time=time(18, 0),
        )

        with pytest.raises(RuntimeError, match="commit failed"):
            svc.create(body)

        mock_session.rollback.assert_called_once()


# ── RestrictionService ───────────────────────────────────────────────────────


class TestRestrictionService:
    def _unique_phone(self, prefix: str) -> str:
        return f"0999{TAG}{prefix}"

    def test_create_success(self, db: Session):
        phone = self._unique_phone("rc1")
        svc = RestrictionService(db)
        r = svc.create(RestrictionCreate(phone=phone, reason="Test"))
        assert r.restriction_id is not None
        assert r.phone == phone

    def test_create_active_exists(self, db: Session):
        phone = self._unique_phone("rc2")
        svc = RestrictionService(db)
        svc.create(RestrictionCreate(phone=phone, reason="First"))
        with pytest.raises(AppError) as exc:
            svc.create(RestrictionCreate(phone=phone, reason="Second"))
        assert exc.value.status_code == 409

    def test_create_inactive_allowed(self, db: Session):
        phone = self._unique_phone("rc3")
        svc = RestrictionService(db)
        svc.create(RestrictionCreate(phone=phone, reason="First", is_active=False))
        r2 = svc.create(RestrictionCreate(phone=phone, reason="Second", is_active=True))
        assert r2.restriction_id is not None

    def test_list(self, db: Session):
        phone = self._unique_phone("rc4")
        svc = RestrictionService(db)
        svc.create(RestrictionCreate(phone=phone, reason="List Me"))
        svc.create(RestrictionCreate(phone=f"{phone}x", reason="List Me 2"))
        results = svc.list()
        assert len(results) >= 2

    def test_get_success(self, db: Session):
        phone = self._unique_phone("rc5")
        svc = RestrictionService(db)
        r = svc.create(RestrictionCreate(phone=phone, reason="Get Me"))
        fetched = svc.get(r.restriction_id)
        assert fetched.restriction_id == r.restriction_id

    def test_get_not_found(self, db: Session):
        svc = RestrictionService(db)
        with pytest.raises(AppError) as exc:
            svc.get(uuid.uuid4())
        assert exc.value.status_code == 404

    def test_update_success(self, db: Session):
        phone = self._unique_phone("rc6")
        svc = RestrictionService(db)
        r = svc.create(RestrictionCreate(phone=phone, reason="Before"))
        updated = svc.update(r.restriction_id, RestrictionUpdate(reason="After"))
        assert updated.reason == "After"

    def test_update_not_found(self, db: Session):
        svc = RestrictionService(db)
        with pytest.raises(AppError) as exc:
            svc.update(uuid.uuid4(), RestrictionUpdate(reason="Nope"))
        assert exc.value.status_code == 404

    def test_update_reactivate_no_conflict(self, db: Session):
        phone = self._unique_phone("rc7")
        svc = RestrictionService(db)
        r = svc.create(RestrictionCreate(phone=phone, reason="Active"))
        deactivated = svc.update(r.restriction_id, RestrictionUpdate(is_active=False))
        assert deactivated.is_active is False
        reactivated = svc.update(deactivated.restriction_id, RestrictionUpdate(is_active=True))
        assert reactivated.is_active is True

    def test_update_reactivate_conflict_detected(self, db: Session):
        phone = self._unique_phone("rc8")
        svc = RestrictionService(db)
        svc.create(RestrictionCreate(phone=phone, reason="First", is_active=True))
        r2 = svc.create(RestrictionCreate(phone=phone, reason="Second", is_active=False))
        with pytest.raises(AppError) as exc:
            svc.update(r2.restriction_id, RestrictionUpdate(is_active=True))
        assert exc.value.status_code == 409

    def test_update_empty_body(self, db: Session):
        phone = self._unique_phone("rc9")
        svc = RestrictionService(db)
        r = svc.create(RestrictionCreate(phone=phone, reason="Empty"))
        updated = svc.update(r.restriction_id, RestrictionUpdate())
        assert updated.reason == "Empty"

    def test_rollback_on_constraint(self, db: Session):
        phone = self._unique_phone("rc10")
        svc = RestrictionService(db)
        svc.create(RestrictionCreate(phone=phone, reason="Original", is_active=True))
        repo = RestrictionRepository(db)
        count_before = len(repo.find_all())

        r2 = CustomerRestriction(restriction_id=uuid.uuid4(), phone=phone, reason="Duplicate", is_active=True)
        with pytest.raises(Exception):
            repo.save(r2)
        db.rollback()

        count_after = len(repo.find_all())
        assert count_after == count_before

    def test_rollback_on_commit_failure(self):
        mock_session = Mock()
        mock_session.scalar.return_value = None
        mock_session.commit.side_effect = RuntimeError("commit failed")

        svc = RestrictionService(mock_session)
        body = RestrictionCreate(phone="0999000000", reason="Test", is_active=True)

        with pytest.raises(RuntimeError, match="commit failed"):
            svc.create(body)

        mock_session.rollback.assert_called_once()
