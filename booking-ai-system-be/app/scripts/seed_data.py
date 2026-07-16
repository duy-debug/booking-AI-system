# Seed dữ liệu mẫu — chạy: python -X utf8 -m app.scripts.seed_data
# Xoá toàn bộ dữ liệu cũ và insert dữ liệu mới sát thực tế

import uuid
import random
from datetime import date, time, timedelta
from decimal import Decimal

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models.shop import Shop
from app.db.models.course import Course
from app.db.models.therapist import Therapist
from app.db.models.therapist_shift import TherapistShift
from app.db.models.customer import Customer
from app.db.models.customer_restriction import CustomerRestriction
from app.db.models.booking import Booking
from app.db.models.reservation import Reservation
from app.db.models.reservation_course import ReservationCourse


engine = create_engine(settings.DATABASE_URL)

# ────────────────────────── DỮ LIỆU MẪU ──────────────────────────

SHOPS = [
    {
        "shop_code": "thien-an-massage",
        "pos_shop_code": "POS-TA-001",
        "name": "Thiên An Massage & Spa",
        "address": "123 Nguyễn Huệ, Quận 1, TP. Hồ Chí Minh",
        "phone": "02838251234",
    },
    {
        "shop_code": "phuc-an-massage",
        "pos_shop_code": "POS-PA-001",
        "name": "Phúc An Massage & Body",
        "address": "456 Lê Lợi, Quận 3, TP. Hồ Chí Minh",
        "phone": "02838255678",
    },
]

COURSES = {
    "thien-an-massage": [
        ("massage-thai", "Massage Thái Cổ Điển", 60, "350000", "main"),
        ("massage-thai-90", "Massage Thái Cổ Điển (90 phút)", 90, "500000", "main"),
        ("massage-da", "Massage Đá Nóng", 60, "400000", "main"),
        ("massage-da-90", "Massage Đá Nóng (90 phút)", 90, "550000", "main"),
        ("massage-thao-duoc", "Massage Thảo Dược", 60, "380000", "main"),
        ("massage-thao-duoc-90", "Massage Thảo Dược (90 phút)", 90, "520000", "main"),
        ("tam-thuoc", "Tắm Thảo Dược", 30, "200000", "addon"),
        ("xong-hoi", "Xông Hơi", 30, "150000", "addon"),
        ("ngam-chan", "Ngâm Chân Thảo Dược", 20, "100000", "addon"),
        ("massage-co-vai-gay", "Massage Cổ Vai Gáy", 30, "180000", "addon"),
    ],
    "phuc-an-massage": [
        ("massage-body", "Massage Body Toàn Thân", 60, "320000", "main"),
        ("massage-body-90", "Massage Body Toàn Thân (90 phút)", 90, "450000", "main"),
        ("massage-sports", "Massage Sports (Thể Thao)", 60, "380000", "main"),
        ("massage-sports-90", "Massage Sports (90 phút)", 90, "520000", "main"),
        ("massage-mo-hinh", "Massage Mô Hình", 60, "400000", "main"),
        ("massage-thai-phuc-hoi", "Massage Thái Phục Hồi", 90, "480000", "main"),
        ("massage-dau-mat", "Massage Đầu - Mặt - Cổ", 30, "160000", "addon"),
        ("massage-tay-chan", "Massage Tay - Chân", 30, "140000", "addon"),
        ("tam-thuoc", "Tắm Thảo Dược", 30, "200000", "addon"),
        ("xong-hoi", "Xông Hơi", 30, "150000", "addon"),
    ],
}

THERAPISTS = {
    "thien-an-massage": [
        ("ther-ta-01", "Nguyễn Thị Lan", "female"),
        ("ther-ta-02", "Trần Thị Hoa", "female"),
        ("ther-ta-03", "Lê Văn Tâm", "male"),
        ("ther-ta-04", "Phạm Thị Ngọc", "female"),
        ("ther-ta-05", "Hoàng Văn Bảo", "male"),
        ("ther-ta-06", "Đỗ Thị Mai", "female"),
        ("ther-ta-07", "Vũ Thị Hạnh", "female"),
        ("ther-ta-08", "Ngô Văn Phúc", "male"),
    ],
    "phuc-an-massage": [
        ("ther-pa-01", "Phan Thị Kim", "female"),
        ("ther-pa-02", "Huỳnh Văn Đức", "male"),
        ("ther-pa-03", "Đặng Thị Thu", "female"),
        ("ther-pa-04", "Bùi Văn Trung", "male"),
        ("ther-pa-05", "Trương Thị Ánh", "female"),
        ("ther-pa-06", "Lý Văn Hùng", "male"),
        ("ther-pa-07", "Mai Thị Phượng", "female"),
    ],
}

SHIFT_SLOTS = [
    (time(8, 0), time(12, 0)),
    (time(9, 0), time(13, 0)),
    (time(12, 0), time(17, 0)),
    (time(13, 0), time(18, 0)),
    (time(17, 0), time(21, 0)),
    (time(18, 0), time(22, 0)),
]

CUSTOMERS = [
    {"phone": "0901234567", "name": "Nguyễn Văn An", "is_member": True, "member_rank": "gold", "visit_count": 15},
    {"phone": "0902345678", "name": "Trần Thị Bình", "is_member": True, "member_rank": "silver", "visit_count": 8},
    {"phone": "0903456789", "name": "Lê Hoàng Cường", "is_member": False, "member_rank": None, "visit_count": 3},
    {"phone": "0904567890", "name": "Phạm Minh Đức", "is_member": True, "member_rank": "gold", "visit_count": 22},
    {"phone": "0905678901", "name": "Hoàng Thị Hương", "is_member": False, "member_rank": None, "visit_count": 1},
    {"phone": "0906789012", "name": "Đỗ Văn Khánh", "is_member": True, "member_rank": "silver", "visit_count": 7},
    {"phone": "0907890123", "name": "Vũ Thị Lan", "is_member": False, "member_rank": None, "visit_count": 5},
]

RESTRICTIONS = [
    {"phone": "0911111111", "reason": "Khách hủy lịch nhiều lần không báo trước", "is_active": True},
    {"phone": "0922222222", "reason": "Khách có hành vi quấy rối nhân viên", "is_active": True},
    {"phone": "0911111111", "reason": "Đã hòa giải, mở lại quyền đặt lịch", "is_active": False},
]

BOOKING_SAMPLES = [
    {"shop": "thien-an-massage", "customer_idx": 0, "day_offset": 0, "start": time(9, 0), "course": "massage-thai-90", "therapist_idx": 0},
    {"shop": "thien-an-massage", "customer_idx": 1, "day_offset": 0, "start": time(14, 0), "course": "massage-da", "therapist_idx": 2},
    {"shop": "phuc-an-massage", "customer_idx": 2, "day_offset": 0, "start": time(10, 0), "course": "massage-body-90", "therapist_idx": 0},
    {"shop": "phuc-an-massage", "customer_idx": 3, "day_offset": 1, "start": time(15, 30), "course": "massage-sports", "therapist_idx": 3},
    {"shop": "thien-an-massage", "customer_idx": 4, "day_offset": 1, "start": time(8, 0), "course": "massage-thai", "therapist_idx": 1},
]

# ────────────────────────── SEED ──────────────────────────

def clean(db: Session):
    print("  Xoá dữ liệu cũ...")
    for table in ["reservation_courses", "reservations", "bookings", "therapist_shifts", "therapists", "courses", "shops", "customers", "customer_restrictions"]:
        db.execute(text(f"DELETE FROM {table}"))
    db.commit()

def seed_shops(db: Session) -> dict[str, Shop]:
    print("  Tạo chi nhánh...")
    result = {}
    for d in SHOPS:
        s = Shop(**d, is_active=True)
        db.add(s)
        db.flush()
        result[d["shop_code"]] = s
    return result

def seed_courses(db: Session, shops: dict[str, Shop]):
    print("  Tạo dịch vụ...")
    for shop_code, items in COURSES.items():
        shop = shops[shop_code]
        for code, name, duration, price_str, ctype in items:
            db.add(Course(shop_id=shop.shop_id, pos_course_code=code, name=name,
                          duration_minutes=duration, price=Decimal(price_str), course_type=ctype, is_active=True))
    db.flush()

def seed_therapists(db: Session, shops: dict[str, Shop]) -> dict[str, list[Therapist]]:
    print("  Tạo therapist...")
    result = {}
    for shop_code, items in THERAPISTS.items():
        shop = shops[shop_code]
        lst = []
        for code, name, gender in items:
            t = Therapist(shop_id=shop.shop_id, pos_therapist_code=code, name=name, gender=gender, is_active=True)
            db.add(t)
            db.flush()
            lst.append(t)
        result[shop_code] = lst
    return result

def seed_shifts(db: Session, shops: dict[str, Shop], therapists: dict[str, list[Therapist]]):
    print("  Tạo ca làm...")
    today = date.today()
    for shop_code, tlist in therapists.items():
        shop = shops[shop_code]
        for t in tlist:
            for offset in range(14):
                d = today + timedelta(days=offset)
                if d.weekday() == 6:
                    continue
                start_t, end_t = random.choice(SHIFT_SLOTS)
                db.add(TherapistShift(therapist_id=t.therapist_id, shop_id=shop.shop_id,
                                      work_date=d, start_time=start_t, end_time=end_t, is_active=True))
    db.flush()

def seed_customers(db: Session) -> list[Customer]:
    print("  Tạo khách hàng...")
    customers = []
    for d in CUSTOMERS:
        c = Customer(phone=d["phone"], name=d["name"], pos_customer_code=f"CUS-{d['phone'][-4:]}",
                     is_member=d["is_member"], member_rank=d["member_rank"], visit_count=d["visit_count"])
        db.add(c)
        db.flush()
        customers.append(c)
    return customers

def seed_restrictions(db: Session):
    print("  Tạo NG list...")
    for d in RESTRICTIONS:
        db.add(CustomerRestriction(**d))
    db.flush()

def seed_bookings(db: Session, shops: dict[str, Shop], customers: list[Customer], therapists: dict[str, list[Therapist]]):
    print("  Tạo booking mẫu...")
    for i, bd in enumerate(BOOKING_SAMPLES):
        shop = shops[bd["shop"]]
        customer = customers[bd["customer_idx"]]
        booking_date = date.today() + timedelta(days=bd["day_offset"])
        start_t = bd["start"]

        course = db.query(Course).filter(Course.shop_id == shop.shop_id, Course.pos_course_code == bd["course"]).first()
        if not course:
            continue

        duration = course.duration_minutes
        total_min = start_t.hour * 60 + start_t.minute + duration
        end_t = time(total_min // 60 % 24, total_min % 60)

        therapist = therapists[bd["shop"]][bd["therapist_idx"] % len(therapists[bd["shop"]])]

        booking = Booking(
            shop_id=shop.shop_id, customer_id=customer.customer_id,
            pos_booking_code=f"BK-{booking_date.strftime('%y%m%d')}-{i+1:03d}",
            pos_sync_status="synced", booking_date=booking_date,
            start_time=start_t, end_time=end_t, number_of_people=1,
            total_duration_minutes=duration, status="confirmed", therapist_request_type="none",
            idempotency_key=uuid.uuid4(),
        )
        db.add(booking)
        db.flush()

        res = Reservation(booking_id=booking.booking_id, person_index=1,
                          therapist_id=therapist.therapist_id, start_time=start_t, end_time=end_t, status="assigned")
        db.add(res)
        db.flush()

        db.add(ReservationCourse(reservation_id=res.reservation_id, course_id=course.course_id,
                                 course_role="main", duration_snapshot=course.duration_minutes,
                                 price_snapshot=course.price, course_name_snapshot=course.name))
    db.flush()

def main():
    print("=== Seed dữ liệu mẫu ===")
    with Session(engine) as db:
        clean(db)
        shops = seed_shops(db)
        seed_courses(db, shops)
        therapists = seed_therapists(db, shops)
        seed_shifts(db, shops, therapists)
        customers = seed_customers(db)
        seed_restrictions(db)
        seed_bookings(db, shops, customers, therapists)
        db.commit()

    total_courses = sum(len(v) for v in COURSES.values())
    total_therapists = sum(len(v) for v in THERAPISTS.values())
    print(f"\n✅ Seed hoàn tất!")
    print(f"   - {len(SHOPS)} chi nhánh")
    print(f"   - {total_courses} dịch vụ")
    print(f"   - {total_therapists} therapist")
    print(f"   - {len(CUSTOMERS)} khách hàng")
    print(f"   - {len(RESTRICTIONS)} NG list")
    print(f"   - {len(BOOKING_SAMPLES)} booking mẫu")
    print(f"   - Ca làm: 6 ngày/tuần x 2 tuần")

if __name__ == "__main__":
    main()
