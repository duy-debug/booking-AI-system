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
from app.scripts.seed_catalog_vi import (
    COURSE_TEMPLATES as VIETNAMESE_COURSE_TEMPLATES,
    FEMALE_NAMES as VIETNAMESE_FEMALE_NAMES,
    MALE_NAMES as VIETNAMESE_MALE_NAMES,
    RESTRICTIONS as VIETNAMESE_RESTRICTIONS,
    SHOPS as VIETNAMESE_SHOPS,
    SURNAMES as VIETNAMESE_SURNAMES,
)


engine = create_engine(settings.DATABASE_URL)

# ────────────────────────── DỮ LIỆU MẪU ──────────────────────────

SHOPS = [
    {
        "shop_code": "tokyo-sakura",
        "pos_shop_code": "POS-TK-001",
        "name": "東京さくらリラクゼーション",
        "address": "東京都渋谷区神宮前一丁目十二番地",
        "phone": "0312345678",
        "therapist_break_minutes": 5,
    },
    {
        "shop_code": "osaka-nagomi",
        "pos_shop_code": "POS-OS-001",
        "name": "大阪なごみ温泉スパ",
        "address": "大阪府大阪市北区梅田二丁目五番地",
        "phone": "0661234567",
        "therapist_break_minutes": 10,
    },
    {
        "shop_code": "kyoto-tsukikage",
        "pos_shop_code": "POS-KY-001",
        "name": "京都月影癒やし処",
        "address": "京都府京都市東山区祇園町南側五百七十番地",
        "phone": "0751234567",
        "therapist_break_minutes": 15,
    },
    {
        "shop_code": "yokohama-minato",
        "pos_shop_code": "POS-YH-001",
        "name": "横浜みなと整体院",
        "address": "神奈川県横浜市中区山下町百番地",
        "phone": "0451234567",
        "therapist_break_minutes": 5,
    },
    {
        "shop_code": "sapporo-yuki",
        "pos_shop_code": "POS-SP-001",
        "name": "札幌雪の華スパ",
        "address": "北海道札幌市中央区北一条西三丁目",
        "phone": "0111234567",
        "therapist_break_minutes": 10,
    },
    {
        "shop_code": "fukuoka-hakata",
        "pos_shop_code": "POS-FK-001",
        "name": "福岡博多くつろぎ庵",
        "address": "福岡県福岡市博多区博多駅前三丁目",
        "phone": "0921234567",
        "therapist_break_minutes": 15,
    },
    {
        "shop_code": "nagoya-aoi",
        "pos_shop_code": "POS-NG-001",
        "name": "名古屋葵リフレッシュ館",
        "address": "愛知県名古屋市中区栄三丁目十五番地",
        "phone": "0521234567",
        "therapist_break_minutes": 5,
    },
    {
        "shop_code": "kobe-rokkou",
        "pos_shop_code": "POS-KB-001",
        "name": "神戸六甲やすらぎの森",
        "address": "兵庫県神戸市中央区三宮町一丁目",
        "phone": "0781234567",
        "therapist_break_minutes": 10,
    },
    {
        "shop_code": "sendai-aoba",
        "pos_shop_code": "POS-SD-001",
        "name": "仙台青葉健康サロン",
        "address": "宮城県仙台市青葉区中央二丁目",
        "phone": "0221234567",
        "therapist_break_minutes": 15,
    },
    {
        "shop_code": "hiroshima-momiji",
        "pos_shop_code": "POS-HS-001",
        "name": "広島もみじ癒やし館",
        "address": "広島県広島市中区紙屋町一丁目",
        "phone": "0821234567",
        "therapist_break_minutes": 5,
    },
    {
        "shop_code": "kanazawa-kaga",
        "pos_shop_code": "POS-KZ-001",
        "name": "金沢加賀美人の湯",
        "address": "石川県金沢市香林坊二丁目",
        "phone": "0761234567",
        "therapist_break_minutes": 10,
    },
    {
        "shop_code": "naha-chura",
        "pos_shop_code": "POS-NH-001",
        "name": "那覇ちゅら海リラクゼーション",
        "address": "沖縄県那覇市久茂地三丁目",
        "phone": "0981234567",
        "therapist_break_minutes": 15,
    },
    {
        "shop_code": "chiba-narita",
        "pos_shop_code": "POS-CB-001",
        "name": "千葉成田和みの間",
        "address": "千葉県成田市花崎町八百三十九番地",
        "phone": "0431234567",
        "therapist_break_minutes": 5,
    },
    {
        "shop_code": "saitama-omiya",
        "pos_shop_code": "POS-ST-001",
        "name": "埼玉大宮癒やし小町",
        "address": "埼玉県さいたま市大宮区桜木町一丁目",
        "phone": "0481234567",
        "therapist_break_minutes": 10,
    },
    {
        "shop_code": "niigata-shinano",
        "pos_shop_code": "POS-NI-001",
        "name": "新潟しなの健康処",
        "address": "新潟県新潟市中央区万代一丁目",
        "phone": "0251234567",
        "therapist_break_minutes": 15,
    },
    {
        "shop_code": "shizuoka-fuji",
        "pos_shop_code": "POS-SZ-001",
        "name": "静岡富士見リラクゼーション",
        "address": "静岡県静岡市葵区御幸町十丁目",
        "phone": "0541234567",
        "therapist_break_minutes": 5,
    },
    {
        "shop_code": "okayama-koraku",
        "pos_shop_code": "POS-OY-001",
        "name": "岡山後楽やすらぎ庵",
        "address": "岡山県岡山市北区駅元町一丁目",
        "phone": "0861234567",
        "therapist_break_minutes": 10,
    },
    {
        "shop_code": "kagoshima-sakurajima",
        "pos_shop_code": "POS-KG-001",
        "name": "鹿児島桜島温浴院",
        "address": "鹿児島県鹿児島市中央町一番地",
        "phone": "0991234567",
        "therapist_break_minutes": 15,
    },
    {
        "shop_code": "kumamoto-aso",
        "pos_shop_code": "POS-KM-001",
        "name": "熊本阿蘇くつろぎ館",
        "address": "熊本県熊本市中央区上通町二丁目",
        "phone": "0961234567",
        "therapist_break_minutes": 5,
    },
    {
        "shop_code": "matsuyama-dogo",
        "pos_shop_code": "POS-MY-001",
        "name": "松山道後湯けむり処",
        "address": "愛媛県松山市道後湯之町五丁目",
        "phone": "0891234567",
        "therapist_break_minutes": 10,
    },
]

COURSE_TEMPLATES = [
    ("body-care-60", "全身もみほぐし六十分", 60, "6500", "main"),
    ("body-care-90", "全身もみほぐし九十分", 90, "9000", "main"),
    ("thai-care-60", "タイ古式施術六十分", 60, "7500", "main"),
    ("thai-care-90", "タイ古式施術九十分", 90, "10500", "main"),
    ("aroma-oil-60", "香り油全身施術六十分", 60, "8500", "main"),
    ("aroma-oil-90", "香り油全身施術九十分", 90, "12000", "main"),
    ("hot-stone-60", "温石療法六十分", 60, "9000", "main"),
    ("hot-stone-90", "温石療法九十分", 90, "12500", "main"),
    ("herbal-footbath", "薬草足湯", 30, "2500", "addon"),
    ("head-spa", "頭皮温浴", 30, "3500", "addon"),
    ("neck-shoulder", "首肩集中ほぐし", 30, "3000", "addon"),
    ("steam-sauna", "薬草蒸し風呂", 30, "2800", "addon"),
]

SHOPS = VIETNAMESE_SHOPS
COURSE_TEMPLATES = VIETNAMESE_COURSE_TEMPLATES

COURSES = {
    shop["shop_code"]: list(COURSE_TEMPLATES)
    for shop in SHOPS
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


# Sinh danh sách kỹ thuật viên tên Việt cho từng cửa hàng với mã POS và giới tính.
def build_therapists() -> dict[str, list[tuple[str, str, str]]]:
    result = {}
    for shop_index, shop_code in enumerate(COURSES):
        prefix = f"s{shop_index + 1:02d}"
        employees = []
        for index in range(THERAPISTS_PER_SHOP):
            gender = "female" if index % 2 == 0 else "male"
            given_names = (
                VIETNAMESE_FEMALE_NAMES
                if gender == "female"
                else VIETNAMESE_MALE_NAMES
            )
            surname = VIETNAMESE_SURNAMES[
                (index + shop_index * 17) % len(VIETNAMESE_SURNAMES)
            ]
            given_name = given_names[(index * 3 + shop_index * 7) % len(given_names)]
            employees.append(
                (f"ther-{prefix}-{index + 1:02d}", f"{surname} {given_name}", gender)
            )
        result[shop_code] = employees
    return result


# Sinh tập khách hàng Việt có số điện thoại duy nhất, hạng thành viên và lịch sử ghé thăm đa dạng.
def build_customers() -> list[dict]:
    customers = []
    all_given_names = VIETNAMESE_FEMALE_NAMES + VIETNAMESE_MALE_NAMES
    for index in range(CUSTOMER_COUNT):
        surname = VIETNAMESE_SURNAMES[index % len(VIETNAMESE_SURNAMES)]
        given_name = all_given_names[
            (index * 7 + index // len(VIETNAMESE_SURNAMES)) % len(all_given_names)
        ]
        is_member = index % 4 != 3
        member_rank = "Hạng Vàng" if index % 12 == 0 else "Hạng Bạc" if is_member else None
        phone_prefix = ("032", "076", "090")[index % 3]
        customers.append({
            "phone": f"{phone_prefix}{index + 1:07d}",
            "name": f"{surname} {given_name}",
            "is_member": is_member,
            "member_rank": member_rank,
            "visit_count": (index * 7) % 48,
        })
    return customers


THERAPISTS = build_therapists()
CUSTOMERS = build_customers()

RESTRICTIONS = [
    {
        "phone": "07000000001",
        "reason": "無断キャンセルを繰り返したため",
        "is_active": True,
    },
    {
        "phone": "08000000002",
        "reason": "従業員への迷惑行為が確認されたため",
        "is_active": True,
    },
    {
        "phone": "09000000003",
        "reason": "支払いに関する問題が解決していないため",
        "is_active": True,
    },
    {
        "phone": "07000000004",
        "reason": "本人確認が完了していないため",
        "is_active": True,
    },
    {
        "phone": "08000000005",
        "reason": "店舗との話し合いにより利用制限を解除",
        "is_active": False,
    },
    {
        "phone": "09000000006",
        "reason": "予約規約への同意が確認できないため",
        "is_active": True,
    },
]

RESTRICTIONS = VIETNAMESE_RESTRICTIONS

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
