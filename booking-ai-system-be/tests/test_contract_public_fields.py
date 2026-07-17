import uuid

from fastapi.testclient import TestClient


PUBLIC_SHOP_FORBIDDEN = {"pos_shop_code", "is_active", "created_at", "updated_at"}
PUBLIC_COURSE_FORBIDDEN = {"pos_course_code", "is_active", "created_at", "updated_at"}
PUBLIC_BOOKING_FORBIDDEN = {"pos_booking_code", "pos_sync_status"}

ADMIN_SHOP_REQUIRED = {"shop_id", "shop_code", "pos_shop_code", "name", "is_active", "created_at", "updated_at"}
ADMIN_COURSE_REQUIRED = {"course_id", "shop_id", "pos_course_code", "name", "duration_minutes", "price", "course_type", "is_active", "created_at", "updated_at"}


class TestPublicShopContract:

    def test_list_public_shops_no_internal_fields(self, client: TestClient, test_data: dict):
        r = client.get("/api/shops")
        assert r.status_code == 200
        for shop in r.json()["data"]:
            keys = set(shop.keys())
            assert keys.isdisjoint(PUBLIC_SHOP_FORBIDDEN), f"Public shop contains forbidden fields: {keys & PUBLIC_SHOP_FORBIDDEN}"
            assert "shop_id" in keys
            assert "shop_code" in keys
            assert "name" in keys

    def test_get_public_shop_no_internal_fields(self, client: TestClient, test_data: dict):
        r = client.get(f"/api/shops/{test_data['shop_id']}")
        assert r.status_code == 200
        keys = set(r.json()["data"].keys())
        assert keys.isdisjoint(PUBLIC_SHOP_FORBIDDEN), f"Public shop detail contains forbidden fields: {keys & PUBLIC_SHOP_FORBIDDEN}"

    def test_list_public_courses_no_internal_fields(self, client: TestClient, test_data: dict):
        r = client.get(f"/api/shops/{test_data['shop_id']}/courses")
        assert r.status_code == 200
        for course in r.json()["data"]:
            keys = set(course.keys())
            assert keys.isdisjoint(PUBLIC_COURSE_FORBIDDEN), f"Public course contains forbidden fields: {keys & PUBLIC_COURSE_FORBIDDEN}"

    def test_get_public_booking_no_internal_fields(self, client: TestClient, test_data: dict):
        body = {
            "shop_id": test_data["shop_id"],
            "booking_date": "2026-07-20",
            "start_time": "11:00",
            "number_of_people": 1,
            "customer": {"phone": test_data["phone"], "name": "Contract Test"},
            "courses": [{"course_id": test_data["course_id"], "course_role": "main"}],
            "therapist_request": {"type": "none"},
            "confirmed_by_customer": True,
        }
        r = client.post("/api/bookings", json=body, headers={"Idempotency-Key": str(uuid.uuid4())})
        assert r.status_code == 201
        keys = set(r.json()["data"].keys())
        assert keys.isdisjoint(PUBLIC_BOOKING_FORBIDDEN), f"Public booking detail contains forbidden fields: {keys & PUBLIC_BOOKING_FORBIDDEN}"

    def test_list_public_bookings_no_internal_fields(self, client: TestClient, test_data: dict):
        r = client.get("/api/bookings", params={"phone": test_data["phone"]})
        assert r.status_code == 200
        for booking in r.json()["data"]:
            keys = set(booking.keys())
            assert keys.isdisjoint(PUBLIC_BOOKING_FORBIDDEN), f"Public booking list item contains forbidden fields: {keys & PUBLIC_BOOKING_FORBIDDEN}"


class TestAdminShopContract:

    def test_list_admin_shops_has_all_fields(self, client: TestClient, auth_headers: dict, test_data: dict):
        r = client.get("/api/admin/shops", headers=auth_headers)
        assert r.status_code == 200
        for shop in r.json()["data"]:
            keys = set(shop.keys())
            assert ADMIN_SHOP_REQUIRED.issubset(keys), f"Admin shop missing fields: {ADMIN_SHOP_REQUIRED - keys}"

    def test_get_admin_shop_has_all_fields(self, client: TestClient, auth_headers: dict, test_data: dict):
        r = client.get(f"/api/admin/shops/{test_data['shop_id']}", headers=auth_headers)
        assert r.status_code == 200
        keys = set(r.json()["data"].keys())
        assert ADMIN_SHOP_REQUIRED.issubset(keys), f"Admin shop detail missing fields: {ADMIN_SHOP_REQUIRED - keys}"


class TestAdminCourseContract:

    def test_list_admin_courses_has_all_fields(self, client: TestClient, auth_headers: dict, test_data: dict):
        r = client.get(f"/api/admin/shops/{test_data['shop_id']}/courses", headers=auth_headers)
        assert r.status_code == 200
        for course in r.json()["data"]:
            keys = set(course.keys())
            assert ADMIN_COURSE_REQUIRED.issubset(keys), f"Admin course missing fields: {ADMIN_COURSE_REQUIRED - keys}"

    def test_get_admin_course_has_all_fields(self, client: TestClient, auth_headers: dict, test_data: dict):
        r = client.get(f"/api/admin/courses/{test_data['course_id']}", headers=auth_headers)
        assert r.status_code == 200
        keys = set(r.json()["data"].keys())
        assert ADMIN_COURSE_REQUIRED.issubset(keys), f"Admin course detail missing fields: {ADMIN_COURSE_REQUIRED - keys}"
