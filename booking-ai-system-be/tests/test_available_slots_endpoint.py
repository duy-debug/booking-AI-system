from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.api.public import available_slots as available_slots_api
from app.main import app


@pytest.fixture
def client():
    app.dependency_overrides[get_db] = lambda: object()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_available_slots_endpoint_accepts_service_dict(monkeypatch, client: TestClient):
    shop_id = uuid4()
    course_id = uuid4()

    class FakeSlotService:
        def __init__(self, session) -> None:
            self.session = session

        def list_available_slots(self, **kwargs):
            return {
                "data": [
                    {
                        "start_time": "10:00",
                        "end_time": "11:00",
                        "duration_minutes": 60,
                        "available": True,
                        "reason_code": None,
                        "message": None,
                        "available_therapist_count": 1,
                        "required_therapist_count": 1,
                    }
                ],
                "meta": {
                    "booking_date": "2026-08-08",
                    "shop_id": str(kwargs["shop_id"]),
                    "number_of_people": 1,
                },
            }

    monkeypatch.setattr(available_slots_api, "SlotService", FakeSlotService)

    response = client.get(
        f"/api/shops/{shop_id}/available-slots",
        params={
            "booking_date": "2026-08-08",
            "number_of_people": 1,
            "main_course_id": str(course_id),
            "therapist_request_type": "none",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"][0]["start_time"] == "10:00:00"
    assert response.json()["meta"]["shop_id"] == str(shop_id)


def test_available_slots_endpoint_allows_empty_data(monkeypatch, client: TestClient):
    shop_id = uuid4()
    course_id = uuid4()

    class FakeSlotService:
        def __init__(self, session) -> None:
            self.session = session

        def list_available_slots(self, **kwargs):
            return {
                "data": [],
                "meta": {
                    "booking_date": "2026-08-08",
                    "shop_id": str(kwargs["shop_id"]),
                    "number_of_people": 1,
                },
            }

    monkeypatch.setattr(available_slots_api, "SlotService", FakeSlotService)

    response = client.get(
        f"/api/shops/{shop_id}/available-slots",
        params={
            "booking_date": "2026-08-08",
            "number_of_people": 1,
            "main_course_id": str(course_id),
            "therapist_request_type": "none",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"] == []
    assert response.json()["meta"]["number_of_people"] == 1
