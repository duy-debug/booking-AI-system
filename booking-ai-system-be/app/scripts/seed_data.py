# Seed dữ liệu mẫu — chạy: python -X utf8 -m app.scripts.seed_data
# Xoá toàn bộ dữ liệu cũ và insert dữ liệu mới sát thực tế

import uuid
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

JAPANESE_SURNAMES = [
    "佐藤", "鈴木", "高橋", "田中", "伊藤", "渡辺", "山本", "中村",
    "小林", "加藤", "吉田", "山田", "佐々木", "山口", "松本", "井上",
    "木村", "林", "斎藤", "清水", "山崎", "森", "池田", "橋本",
    "阿部", "石川", "山下", "中島", "石井", "小川", "前田", "岡田",
    "長谷川", "藤田", "後藤", "近藤", "村上", "遠藤", "青木", "坂本",
]

JAPANESE_FEMALE_NAMES = [
    "美咲", "陽菜", "葵", "結衣", "さくら", "凛", "愛", "七海",
    "彩花", "優奈", "美月", "花", "莉子", "杏", "千尋", "直子",
    "恵", "由美", "真央", "玲奈", "香織", "麻衣", "明日香", "奈々",
    "綾乃", "遥", "桃子", "ひなた", "楓", "琴音",
]

JAPANESE_MALE_NAMES = [
    "蓮", "大翔", "翔太", "悠真", "陽斗", "健太", "拓海", "直樹",
    "大輔", "和也", "誠", "亮", "優斗", "陸", "颯太", "一樹",
    "達也", "雄大", "海斗", "浩二", "修平", "智也", "雅人", "健一",
    "隆", "学", "仁", "湊", "樹", "朝陽",
]

THERAPISTS_PER_SHOP = 24
CUSTOMER_COUNT = 240
SEED_DAYS = 21


# Sinh danh sách therapist tên Nhật cho từng shop với mã POS, giới tính và tên không bị lệch chỉ số.
def build_therapists() -> dict[str, list[tuple[str, str, str]]]:
    result = {}
    for shop_index, shop_code in enumerate(COURSES):
        prefix = "ta" if shop_code == "thien-an-massage" else "pa"
        employees = []
        for index in range(THERAPISTS_PER_SHOP):
            gender = "female" if index % 2 == 0 else "male"
            given_names = (
                JAPANESE_FEMALE_NAMES if gender == "female" else JAPANESE_MALE_NAMES
            )
            surname = JAPANESE_SURNAMES[(index + shop_index * 17) % len(JAPANESE_SURNAMES)]
            given_name = given_names[(index * 3 + shop_index * 7) % len(given_names)]
            employees.append(
                (f"ther-{prefix}-{index + 1:02d}", f"{surname} {given_name}", gender)
            )
        result[shop_code] = employees
    return result


# Sinh tập khách hàng Nhật có số điện thoại duy nhất, hạng thành viên và lịch sử ghé thăm đa dạng.
def build_customers() -> list[dict]:
    customers = []
    all_given_names = JAPANESE_FEMALE_NAMES + JAPANESE_MALE_NAMES
    for index in range(CUSTOMER_COUNT):
        surname = JAPANESE_SURNAMES[index % len(JAPANESE_SURNAMES)]
        given_name = all_given_names[(index * 7 + index // len(JAPANESE_SURNAMES)) % len(all_given_names)]
        is_member = index % 4 != 3
        member_rank = "gold" if index % 12 == 0 else "silver" if is_member else None
        phone_prefix = ("070", "080", "090")[index % 3]
        customers.append({
            "phone": f"{phone_prefix}{index + 1:08d}",
            "name": f"{surname} {given_name}",
            "is_member": is_member,
            "member_rank": member_rank,
            "visit_count": (index * 7) % 48,
        })
    return customers


THERAPISTS = build_therapists()
CUSTOMERS = build_customers()

RESTRICTIONS = [
    {"phone": "0911111111", "reason": "Khách hủy lịch nhiều lần không báo trước", "is_active": True},
    {"phone": "0922222222", "reason": "Khách có hành vi quấy rối nhân viên", "is_active": True},
    {"phone": "0911111111", "reason": "Đã hòa giải, mở lại quyền đặt lịch", "is_active": False},
]

BOOKING_START_TIMES = [
    time(9, 0), time(10, 30), time(12, 0), time(14, 0),
    time(15, 30), time(17, 0), time(18, 30), time(20, 0),
]

# ────────────────────────── SEED ──────────────────────────

def clean(db: Session):
    print("  Xoá dữ liệu cũ...")
    for table in ["reservation_courses", "reservations", "bookings", "therapist_shifts", "therapists", "courses", "shops", "customers", "customer_restrictions"]:
        db.execute(text(f"DELETE FROM {table}"))
    db.commit()

# Tạo các shop hoạt động, flush để lấy khóa chính và trả map theo shop_code cho các bước seed sau.
def seed_shops(db: Session) -> dict[str, Shop]:
    print("  Tạo chi nhánh...")
    result = {}
    for d in SHOPS:
        s = Shop(**d, is_active=True)
        db.add(s)
        db.flush()
        result[d["shop_code"]] = s
    return result

# Tạo main course và add-on đúng shop, đồng thời chuyển giá cấu hình sang Decimal trước khi lưu.
def seed_courses(db: Session, shops: dict[str, Shop]):
    print("  Tạo dịch vụ...")
    for shop_code, items in COURSES.items():
        shop = shops[shop_code]
        for code, name, duration, price_str, ctype in items:
            db.add(Course(shop_id=shop.shop_id, pos_course_code=code, name=name,
                          duration_minutes=duration, price=Decimal(price_str), course_type=ctype, is_active=True))
    db.flush()

# Tạo therapist cho từng shop và trả danh sách model đã có ID để seed shift và reservation.
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

# Tạo ca làm toàn ngày trong ba tuần cho từng therapist, bỏ qua Chủ nhật theo lịch vận hành mẫu.
def seed_shifts(db: Session, shops: dict[str, Shop], therapists: dict[str, list[Therapist]]):
    print("  Tạo ca làm...")
    today = date.today()
    for shop_code, tlist in therapists.items():
        shop = shops[shop_code]
        for t in tlist:
            for offset in range(SEED_DAYS):
                d = today + timedelta(days=offset)
                if d.weekday() == 6:
                    continue
                db.add(TherapistShift(therapist_id=t.therapist_id, shop_id=shop.shop_id,
                                      work_date=d, start_time=time(8), end_time=time(22), is_active=True))
    db.flush()

# Lưu toàn bộ khách hàng mẫu và trả model đã flush để liên kết luân phiên với các booking.
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

# Tạo cả hạn chế đang hiệu lực và lịch sử hạn chế đã gỡ để kiểm thử NG list.
def seed_restrictions(db: Session):
    print("  Tạo NG list...")
    for d in RESTRICTIONS:
        db.add(CustomerRestriction(**d))
    db.flush()

# Sinh booking đơn và nhóm không trùng therapist, kèm course snapshot và nguồn phân công auto.
def seed_bookings(
    db: Session,
    shops: dict[str, Shop],
    customers: list[Customer],
    therapists: dict[str, list[Therapist]],
) -> int:
    print("  Tạo booking mẫu...")
    booking_number = 0
    today = date.today()

    for shop_index, (shop_code, shop) in enumerate(shops.items()):
        shop_courses = db.query(Course).filter(Course.shop_id == shop.shop_id).all()
        main_courses = [course for course in shop_courses if course.course_type == "main"]
        addons = [course for course in shop_courses if course.course_type == "addon"]
        shop_therapists = therapists[shop_code]

        for day_offset in range(SEED_DAYS):
            booking_date = today + timedelta(days=day_offset)
            if booking_date.weekday() == 6:
                continue

            for slot_index, start_t in enumerate(BOOKING_START_TIMES):
                booking_number += 1
                main_course = main_courses[
                    (booking_number + slot_index + shop_index) % len(main_courses)
                ]
                selected_courses = [main_course]
                if booking_number % 4 == 0:
                    selected_courses.append(addons[booking_number % len(addons)])

                duration = sum(course.duration_minutes for course in selected_courses)
                total_min = start_t.hour * 60 + start_t.minute + duration
                end_t = time(total_min // 60 % 24, total_min % 60)
                number_of_people = (1, 1, 2, 1, 3)[booking_number % 5]
                customer = customers[(booking_number * 7 + shop_index) % len(customers)]
                status = "cancelled" if booking_number % 13 == 0 else "confirmed"

                booking = Booking(
                    shop_id=shop.shop_id,
                    customer_id=customer.customer_id,
                    pos_booking_code=f"BK-{booking_date.strftime('%y%m%d')}-{booking_number:04d}",
                    pos_sync_status="synced",
                    booking_date=booking_date,
                    start_time=start_t,
                    end_time=end_t,
                    number_of_people=number_of_people,
                    total_duration_minutes=duration,
                    status=status,
                    therapist_request_type="none",
                    idempotency_key=uuid.uuid4(),
                )
                db.add(booking)
                db.flush()

                therapist_start = (booking_number * 3) % len(shop_therapists)
                for person_index in range(1, number_of_people + 1):
                    assigned_therapist = shop_therapists[
                        (therapist_start + person_index - 1) % len(shop_therapists)
                    ]
                    reservation = Reservation(
                        booking_id=booking.booking_id,
                        person_index=person_index,
                        therapist_id=assigned_therapist.therapist_id,
                        start_time=start_t,
                        end_time=end_t,
                        status="assigned",
                        assignment_source="auto",
                    )
                    db.add(reservation)
                    db.flush()

                    for course in selected_courses:
                        db.add(ReservationCourse(
                            reservation_id=reservation.reservation_id,
                            course_id=course.course_id,
                            course_role=course.course_type,
                            duration_snapshot=course.duration_minutes,
                            price_snapshot=course.price,
                            course_name_snapshot=course.name,
                        ))
    db.flush()
    return booking_number

# Điều phối xóa dữ liệu cũ, seed theo đúng thứ tự khóa ngoại, commit và in thống kê kết quả.
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
        total_bookings = seed_bookings(db, shops, customers, therapists)
        db.commit()

    total_courses = sum(len(v) for v in COURSES.values())
    total_therapists = sum(len(v) for v in THERAPISTS.values())
    print(f"\n✅ Seed hoàn tất!")
    print(f"   - {len(SHOPS)} chi nhánh")
    print(f"   - {total_courses} dịch vụ")
    print(f"   - {total_therapists} therapist")
    print(f"   - {len(CUSTOMERS)} khách hàng")
    print(f"   - {len(RESTRICTIONS)} NG list")
    print(f"   - {total_bookings} booking mẫu (có booking nhóm 2-3 người)")
    print(f"   - Ca làm: 6 ngày/tuần x 3 tuần")

if __name__ == "__main__":
    main()
