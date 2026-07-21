# Integration tests cho GET /api/admin/schedule (resource timeline tổng hợp)
# Căn cứ: yêu cầu endpoint schedule — 1 request trả đủ shop/therapists/shifts/
# blocked_ranges/bookings/statuses/business_hours. Test các trường hợp:
#  - ngày bình thường
#  - lịch qua nửa đêm
#  - therapist không có shift
#  - booking bị cancel
#  - booking chưa gán therapist (therapist_request_type = none)
#  - shop không tồn tại
#  - user không có quyền
import uuid
from datetime import date

import pytest


@pytest.fixture(scope="module")
def schedule_date() -> str:
    return "2026-07-20"


@pytest.fixture(scope="module")
def extra_therapist(client: object, auth_headers: dict, test_data: dict) -> str:
    # Therapist thứ 2 trong shop — KHÔNG tạo shift (để test "không có shift")
    r = client.post(  # type: ignore[attr-defined]
        f"/api/admin/shops/{test_data['shop_id']}/therapists",
        json={
            "pos_therapist_code": f"{test_data['shop_id'][:8]}-th2",
            "name": "Therapist No Shift",
            "gender": "male",
            "is_active": True,
        },
        headers=auth_headers,
    )
    assert r.status_code == 201, f"Create therapist fail: {r.text}"
    return r.json()["data"]["therapist_id"]


def _post_booking(client, auth_headers, test_data, start, end, request_type="none"):
    # Dùng TestClient để post booking (header Idempotency-Key do chúng ta sinh)
    rid = str(uuid.uuid4())
    r = client.post(  # type: ignore[attr-defined]
        "/api/bookings",
        json={
            "shop_id": test_data["shop_id"],
            "booking_date": "2026-07-20",
            "start_time": start,
            "number_of_people": 1,
            "customer": {"phone": f"0911{uuid.uuid4().hex[:6]}", "name": "Sched Cust"},
            "courses": [{"course_id": test_data["course_id"], "course_role": "main"}],
            "therapist_request": {"type": request_type},
            "confirmed_by_customer": True,
        },
        headers={**auth_headers, "Idempotency-Key": rid},
    )
    return r


def test_normal_day(client, auth_headers, test_data, schedule_date):
    r = client.get(  # type: ignore[attr-defined]
        "/api/admin/schedule",
        params={"shop_id": test_data["shop_id"], "date": schedule_date},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["shop"]["shop_id"] == test_data["shop_id"]
    assert d["date"] == schedule_date
    assert d["shop"]["timezone"]
    assert "business_hours" in d["shop"]
    # Therapist có shift từ test_data phải xuất hiện
    tids = {t["therapist_id"] for t in d["therapists"]}
    assert test_data["therapist_id"] in tids
    # Có ít nhất 1 shift active
    assert any(s["is_active"] for s in d["shifts"])
    assert "booking_statuses" in d


def test_midnight_booking(client, auth_headers, test_data, schedule_date):
    _post_booking(client, auth_headers, test_data, "23:00", "01:00")
    r = client.get(  # type: ignore[attr-defined]
        "/api/admin/schedule",
        params={"shop_id": test_data["shop_id"], "date": schedule_date},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    # Phải có ít nhất 1 booking/spans_midnight = true
    spans = [b for b in d["bookings"] if b["spans_midnight"]]
    assert spans, "phải có booking qua nửa đêm"
    # view_window mặc định cũng phải nhận biết qua nửa đêm nếu close<open
    # (business hours từ shift 09-18 nên không spans; booking riêng spans)
    assert spans[0]["end_time"] == "01:00"


def test_therapist_without_shift(client, auth_headers, test_data, extra_therapist, schedule_date):
    r = client.get(  # type: ignore[attr-defined]
        "/api/admin/schedule",
        params={"shop_id": test_data["shop_id"], "date": schedule_date},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    tids = {t["therapist_id"] for t in d["therapists"]}
    assert extra_therapist in tids
    # Therapist này không có shift nào
    assert not any(s["therapist_id"] == extra_therapist for s in d["shifts"])
    # Không có booking nào gắn therapist này (vì chưa tạo)
    for b in d["bookings"]:
        for res in b["reservations"]:
            assert res["therapist_id"] != extra_therapist


def test_cancelled_booking(client, auth_headers, test_data, schedule_date):
    rb = _post_booking(client, auth_headers, test_data, "14:00", "15:00")
    assert rb.status_code in (200, 201), rb.text
    bid = rb.json()["data"]["booking_id"]
    rc = client.patch(  # type: ignore[attr-defined]
        f"/api/admin/bookings/{bid}",
        json={"status": "cancelled", "cancel_reason": "test"},
        headers=auth_headers,
    )
    assert rc.status_code == 200, rc.text
    r = client.get(  # type: ignore[attr-defined]
        "/api/admin/schedule",
        params={"shop_id": test_data["shop_id"], "date": schedule_date},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    found = next((b for b in d["bookings"] if b["booking_id"] == bid), None)
    assert found is not None
    assert found["status"] == "cancelled"
    assert "cancelled" in d["booking_statuses"]


def test_unassigned_therapist_request(client, auth_headers, test_data, schedule_date):
    rb = _post_booking(client, auth_headers, test_data, "16:00", "17:00", request_type="none")
    assert rb.status_code in (200, 201), rb.text
    bid = rb.json()["data"]["booking_id"]
    r = client.get(  # type: ignore[attr-defined]
        "/api/admin/schedule",
        params={"shop_id": test_data["shop_id"], "date": schedule_date},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    found = next((b for b in d["bookings"] if b["booking_id"] == bid), None)
    assert found is not None
    assert found["therapist_request_type"] == "none"
    assert found["requested_therapist_id"] is None


def test_shop_not_found(client, auth_headers, schedule_date):
    fake = str(uuid.uuid4())
    r = client.get(  # type: ignore[attr-defined]
        "/api/admin/schedule",
        params={"shop_id": fake, "date": schedule_date},
        headers=auth_headers,
    )
    assert r.status_code == 404
    assert r.json()["code"] == "SHOP_NOT_FOUND"


def test_no_permission(client, auth_headers, test_data, schedule_date, monkeypatch):
    # Tạm thời bỏ email khỏi whitelist -> token hợp lệ nhưng KHÔNG có quyền admin
    from app.core.config import settings

    monkeypatch.setattr(settings, "ADMIN_EMAILS", [])
    r = client.get(  # type: ignore[attr-defined]
        "/api/admin/schedule",
        params={"shop_id": test_data["shop_id"], "date": schedule_date},
        headers=auth_headers,
    )
    assert r.status_code == 403
    assert r.json()["code"] == "FORBIDDEN"


def test_missing_auth(client, test_data, schedule_date):
    r = client.get(  # type: ignore[attr-defined]
        "/api/admin/schedule",
        params={"shop_id": test_data["shop_id"], "date": schedule_date},
    )
    assert r.status_code == 401
