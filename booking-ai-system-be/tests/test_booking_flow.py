# Integration test — Public booking flow: eligibility → create → get → cancel
# Dùng test_data fixture từ conftest.py (session-scoped)

from fastapi.testclient import TestClient


class TestPublicShop:
    """Flow 1: Public endpoints — shop list, courses, available slots"""

    def test_list_public_shops(self, client: TestClient, test_data: dict):
        r = client.get("/api/shops")
        assert r.status_code == 200
        ids = [s["shop_id"] for s in r.json()["data"]]
        assert test_data["shop_id"] in ids

    def test_get_public_shop(self, client: TestClient, test_data: dict):
        r = client.get(f"/api/shops/{test_data['shop_id']}")
        assert r.status_code == 200

    def test_list_public_courses(self, client: TestClient, test_data: dict):
        r = client.get(f"/api/shops/{test_data['shop_id']}/courses")
        assert r.status_code == 200
        ids = [c["course_id"] for c in r.json()["data"]]
        assert test_data["course_id"] in ids

    def test_available_slots(self, client: TestClient, test_data: dict):
        r = client.get(
            f"/api/shops/{test_data['shop_id']}/available-slots",
            params={
                "booking_date": "2026-07-20",
                "number_of_people": 1,
                "main_course_id": test_data["course_id"],
                "therapist_request_type": "none",
            },
        )
        assert r.status_code == 200
        assert len(r.json()["data"]) > 0

    def test_available_therapists(self, client: TestClient, test_data: dict):
        r = client.get(
            f"/api/shops/{test_data['shop_id']}/available-therapists",
            params={
                "booking_date": "2026-07-20",
                "start_time": "10:00",
                "end_time": "11:00",
            },
        )
        assert r.status_code == 200
        ids = [t["therapist_id"] for t in r.json()["data"]]
        assert test_data["therapist_id"] in ids


class TestBookingEligibility:
    """Flow 2: Check eligibility với số điện thoại mới"""

    def test_eligibility_new_customer(self, client: TestClient, test_data: dict):
        r = client.post(
            "/api/booking-eligibility-checks",
            json={"phone": test_data["phone"], "shop_id": test_data["shop_id"]},
        )
        assert r.status_code == 201, f"Eligibility fail: {r.text}"
        data = r.json()["data"]
        assert data["eligible"] is True
        assert data["phone"] == test_data["phone"]
        # Customer mới — chưa có trong DB → customer null
        assert data["customer"] is None or data["customer"].get("customer_id") is None


class TestCreateBooking:
    """Flow 3: Tạo booking thành công + idempotency check"""

    BOOKING_ID: str | None = None

    def test_create_booking(self, client: TestClient, test_data: dict):
        body = {
            "shop_id": test_data["shop_id"],
            "booking_date": "2026-07-20",
            "start_time": "10:00",
            "number_of_people": 1,
            "customer": {"phone": test_data["phone"], "name": "Test Customer"},
            "courses": [{"course_id": test_data["course_id"], "course_role": "main"}],
            "therapist_request": {
                "type": "specific",
                "therapist_id": test_data["therapist_id"],
                "gender": None,
            },
            "confirmed_by_customer": True,
        }
        r = client.post(
            "/api/bookings",
            json=body,
            headers={"Idempotency-Key": test_data["idem_key"]},
        )
        assert r.status_code == 201, f"Create booking fail: {r.text}"
        TestCreateBooking.BOOKING_ID = r.json()["data"]["booking_id"]
        assert r.json()["data"]["booking_code"].startswith("KMB-20260720-")
        assert r.json()["data"]["status"] == "confirmed"
        assert len(r.json()["data"]["reservations"]) > 0
        assert len(r.json()["data"]["reservations"][0]["courses"]) > 0

    def test_idempotency_conflict(self, client: TestClient, test_data: dict):
        # Dùng cùng Idempotency-Key nhưng payload khác → 409
        body = {
            "shop_id": test_data["shop_id"],
            "booking_date": "2026-07-20",
            "start_time": "14:00",
            "number_of_people": 1,
            "customer": {"phone": test_data["phone"], "name": "Test Customer"},
            "courses": [{"course_id": test_data["course_id"], "course_role": "main"}],
            "confirmed_by_customer": True,
        }
        r = client.post(
            "/api/bookings",
            json=body,
            headers={"Idempotency-Key": test_data["idem_key"]},
        )
        assert r.status_code == 409, f"Expected 409, got {r.status_code}: {r.text}"
        assert r.json()["code"] == "SLOT_CONFLICT"


class TestGetBooking:
    """Flow 4: Lấy booking detail + list + reservations"""

    def test_get_booking(self, client: TestClient):
        assert TestCreateBooking.BOOKING_ID
        r = client.get(f"/api/bookings/{TestCreateBooking.BOOKING_ID}")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["status"] == "confirmed"
        assert len(data["reservations"]) > 0

    def test_list_bookings_by_phone(self, client: TestClient, test_data: dict):
        r = client.get("/api/bookings", params={"phone": test_data["phone"]})
        assert r.status_code == 200
        ids = [b["booking_id"] for b in r.json()["data"]]
        assert TestCreateBooking.BOOKING_ID in ids

    def test_list_reservations(self, client: TestClient):
        assert TestCreateBooking.BOOKING_ID
        r = client.get(
            f"/api/bookings/{TestCreateBooking.BOOKING_ID}/reservations"
        )
        assert r.status_code == 200
        assert len(r.json()["data"]) > 0


class TestCancelBooking:
    """Flow 5: Hủy booking + kiểm tra không thể hủy lần 2"""

    def test_cancel_booking(self, client: TestClient):
        assert TestCreateBooking.BOOKING_ID
        r = client.patch(
            f"/api/bookings/{TestCreateBooking.BOOKING_ID}",
            json={"status": "cancelled", "cancel_reason": "Test cancellation"},
        )
        assert r.status_code == 200, f"Cancel fail: {r.text}"
        data = r.json()["data"]
        assert data["status"] == "cancelled"
        assert data["cancel_reason"] is not None

    def test_cancel_already_cancelled(self, client: TestClient):
        assert TestCreateBooking.BOOKING_ID
        r = client.patch(
            f"/api/bookings/{TestCreateBooking.BOOKING_ID}",
            json={"status": "cancelled", "cancel_reason": "Cancel again"},
        )
        assert r.status_code == 409
        assert r.json()["code"] == "BOOKING_ALREADY_CANCELLED"
