# Integration tests cho POS Integration — mock POS client + webhook + availability sync
# Dùng test_data fixture từ conftest.py (session-scoped)

import uuid

from fastapi.testclient import TestClient

from app.core.config import settings
from app.integrations.pos import get_pos_client
from app.integrations.pos.mock import MockPOSClient


class TestPOSClient:
    """Flow 1: POS client mock hoạt động đúng interface"""

    def test_get_pos_client_returns_mock(self):
        # Kiểm tra POS_MODE=mock trả về MockPOSClient
        assert settings.POS_MODE == "mock"
        client = get_pos_client()
        assert isinstance(client, MockPOSClient)

    def test_mock_check_availability(self):
        from datetime import date, time
        client = get_pos_client()
        result = client.check_availability(
            pos_shop_code="SHOP001",
            booking_date=date(2026, 7, 20),
            start_time=time(10, 0),
            end_time=time(11, 0),
            number_of_people=1,
        )
        assert result.available is True
        assert result.slot_start_time == time(10, 0)

    def test_mock_get_available_slots(self):
        from datetime import date
        client = get_pos_client()
        slots = client.get_available_slots(
            pos_shop_code="SHOP001",
            booking_date=date(2026, 7, 20),
            total_duration_minutes=60,
            number_of_people=1,
        )
        assert len(slots) > 0
        assert all(s.available for s in slots)

    def test_mock_create_booking_returns_code(self):
        from datetime import date, time
        from app.integrations.pos.base import POSBookingData

        client = get_pos_client()
        data = POSBookingData(
            pos_shop_code="SHOP001",
            booking_date=date(2026, 7, 20),
            start_time=time(10, 0),
            end_time=time(11, 0),
            number_of_people=1,
            total_duration_minutes=60,
            customer_phone="0900000000",
            customer_name="Test",
            courses=[],
            therapist_ids=None,
        )
        result = client.create_booking(data)
        assert result.success is True
        assert result.pos_booking_code is not None
        assert result.pos_booking_code.startswith("POS-")

    def test_mock_cancel_booking(self):
        from datetime import date, time
        from app.integrations.pos.base import POSBookingData

        client = get_pos_client()
        # Tạo booking trước → cancel sau
        data = POSBookingData(
            pos_shop_code="SHOP001",
            booking_date=date(2026, 7, 20),
            start_time=time(10, 0),
            end_time=time(11, 0),
            number_of_people=1,
            total_duration_minutes=60,
            customer_phone="0900000000",
            customer_name="Test",
            courses=[],
            therapist_ids=None,
        )
        created = client.create_booking(data)
        assert created.success is True

        result = client.cancel_booking(created.pos_booking_code)
        assert result is True


class TestPOSWebhook:
    """Flow 2: POS webhook endpoints — POS gửi push updates"""

    def test_pos_booking_sync_unknown_returns_404(self, client: TestClient):
        # Gửi webhook với booking code không tồn tại → 404
        r = client.post(
            "/api/pos/booking-sync",
            json={"pos_booking_code": "POS-NONEXISTENT", "status": "confirmed"},
        )
        assert r.status_code == 404

    def test_pos_booking_sync_updates_code(self, client: TestClient, test_data: dict):
        # Tạo booking trước, sau đó POS gửi webhook cập nhật code
        pos_code = f"POS-WEBHOOK-{uuid.uuid4().hex[:8].upper()}"
        body = {
            "shop_id": test_data["shop_id"],
            "booking_date": "2026-07-20",
            "start_time": "14:00",
            "number_of_people": 1,
            "customer": {"phone": f"0901{uuid.uuid4().hex[:6]}", "name": "POS Test"},
            "courses": [{"course_id": test_data["course_id"], "course_role": "main"}],
            "confirmed_by_customer": True,
        }
        idem = str(uuid.uuid4())
        r = client.post("/api/bookings", json=body, headers={"Idempotency-Key": idem})
        assert r.status_code == 201
        booking_id = r.json()["data"]["booking_id"]

        # POS gửi webhook cập nhật pos_booking_code
        r = client.post(
            "/api/pos/booking-sync",
            json={
                "pos_booking_code": pos_code,
                "local_booking_id": booking_id,
                "status": "confirmed",
            },
        )
        assert r.status_code == 200
        assert r.json()["booking_id"] == booking_id

        # Verify booking đã được cập nhật
        r = client.get(f"/api/bookings/{booking_id}")
        assert r.json()["data"]["pos_booking_code"] == pos_code
        assert r.json()["data"]["pos_sync_status"] == "synced"

    def test_pos_availability_update(self, client: TestClient):
        # POS gửi cập nhật availability
        r = client.post(
            "/api/pos/availability-update",
            json={
                "pos_shop_code": "SHOP001",
                "booking_date": "2026-07-20",
                "start_time": "10:00",
                "end_time": "11:00",
                "available": False,
            },
        )
        assert r.status_code == 200


class TestPOSBookingSync:
    """Flow 3: Booking flow được đồng bộ POS — pos_booking_code + pos_sync_status"""

    def test_create_booking_gets_pos_code(self, client: TestClient, test_data: dict):
        idem = str(uuid.uuid4())
        body = {
            "shop_id": test_data["shop_id"],
            "booking_date": "2026-07-20",
            "start_time": "15:00",
            "number_of_people": 1,
            "customer": {"phone": f"0902{uuid.uuid4().hex[:6]}", "name": "POS Sync"},
            "courses": [{"course_id": test_data["course_id"], "course_role": "main"}],
            "confirmed_by_customer": True,
        }
        r = client.post("/api/bookings", json=body, headers={"Idempotency-Key": idem})
        assert r.status_code == 201
        data = r.json()["data"]

        # Booking được gán pos_booking_code từ mock POS
        assert data["pos_booking_code"] is not None
        assert data["pos_booking_code"].startswith("POS-")
        assert data["pos_sync_status"] == "synced"

    def test_cancel_updates_pos_sync_status(self, client: TestClient, test_data: dict):
        idem = str(uuid.uuid4())
        body = {
            "shop_id": test_data["shop_id"],
            "booking_date": "2026-07-20",
            "start_time": "16:00",
            "number_of_people": 1,
            "customer": {"phone": f"0903{uuid.uuid4().hex[:6]}", "name": "POS Cancel"},
            "courses": [{"course_id": test_data["course_id"], "course_role": "main"}],
            "confirmed_by_customer": True,
        }
        r = client.post("/api/bookings", json=body, headers={"Idempotency-Key": idem})
        assert r.status_code == 201
        booking_id = r.json()["data"]["booking_id"]

        # Cancel booking → POS sync status = cancelled
        r = client.patch(
            f"/api/bookings/{booking_id}",
            json={"status": "cancelled", "cancel_reason": "POS cancel test"},
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["status"] == "cancelled"
        assert data["pos_sync_status"] == "cancelled"


class TestPOSAvailabilitySync:
    """Flow 4: Available slots có POS data"""

    def test_available_slots_with_pos(self, client: TestClient, test_data: dict):
        # Available slots vẫn trả về kết quả khi có POS sync
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
        slots = r.json()["data"]
        assert len(slots) > 0
