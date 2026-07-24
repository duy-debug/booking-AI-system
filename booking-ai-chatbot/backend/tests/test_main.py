# Tests cho main app: Qdrant startup, KB auth, isolation constraints

import importlib
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient


class TestKBAuth:
    def test_kb_seed_no_auth_returns_401(self, client: TestClient):
        r = client.post("/api/kb/seed")
        assert r.status_code == 401
        assert r.json()["code"] == "UNAUTHORIZED"

    def test_kb_seed_wrong_token_returns_401(self, client: TestClient):
        r = client.post("/api/kb/seed", headers={"Authorization": "Bearer wrong-key"})
        assert r.status_code == 401

    def test_kb_stats_no_auth_returns_401(self, client: TestClient):
        r = client.get("/api/kb/stats")
        assert r.status_code == 401

    def test_kb_stats_wrong_token_returns_401(self, client: TestClient):
        r = client.get("/api/kb/stats", headers={"Authorization": "Bearer wrong"})
        assert r.status_code == 401


class TestIsolation:
    def test_chatbot_does_not_import_db_session(self):
        # Dam bao chatbot KHONG import SQLAlchemy Session hay model cua BE
        import sys

        for mod in list(sys.modules.keys()):
            if "sqlalchemy" in mod or "app.db" in mod or "psycopg2" in mod:
                raise AssertionError(f"Chatbot khong duoc import: {mod}")
        # Import thu app de verify
        try:
            importlib.import_module("app.main")
        except Exception as exc:
            # Chi duoc phep loi Qdrant/network, khong duoc loi SQLAlchemy
            if "sqlalchemy" in str(exc).lower() or "psycopg" in str(exc).lower():
                raise AssertionError(f"Chatbot khong duoc phu thuoc DB: {exc}") from exc

    def test_chatbot_does_not_call_admin_api(self):
        # Kiem tra booking_api chi goi public endpoints
        # Bang cach verify cac method khong chua "admin"
        import inspect

        from app.integrations import booking_api as api

        for name, method in inspect.getmembers(api, inspect.iscoroutinefunction):
            src = inspect.getsource(method)
            if "admin" in src.lower():
                raise AssertionError(f"Method {name} goi admin API: {src}")


class TestHealth:
    def test_health_endpoint(self, client: TestClient):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_root_endpoint(self, client: TestClient):
        r = client.get("/")
        assert r.status_code == 200
        assert "Booking AI Chatbot" in r.json()["message"]


class TestChatContract:
    def test_chat_requires_query_or_selection(self, client: TestClient):
        response = client.post(
            "/api/chat",
            json={"conversation_id": "conversation-1"},
        )

        assert response.status_code == 422
        assert response.json()["code"] == "VALIDATION_ERROR"

    def test_structured_selection_is_forwarded_to_orchestrator(
        self,
        client: TestClient,
    ):
        from app.api.chat import get_orchestrator
        from app.main import app

        orchestrator = AsyncMock()
        orchestrator.handle.return_value = {
            "answer": "Bạn muốn chọn dịch vụ nào?",
            "intent": "create_booking",
            "conversation_id": "conversation-1",
            "missing_entities": ["main_course_id"],
            "ui": {
                "type": "course_options",
                "options": [],
                "data": {},
            },
        }
        app.dependency_overrides[get_orchestrator] = lambda: orchestrator
        try:
            response = client.post(
                "/api/chat",
                json={
                    "conversation_id": "conversation-1",
                    "selection": {
                        "entity": "shop_id",
                        "value": "shop-1",
                    },
                },
            )
        finally:
            app.dependency_overrides.pop(get_orchestrator, None)

        assert response.status_code == 200
        assert response.json()["ui"]["type"] == "course_options"
        orchestrator.handle.assert_awaited_once_with(
            query=None,
            conversation_id="conversation-1",
            selection={
                "entity": "shop_id",
                "value": "shop-1",
                "label": None,
                "metadata": {},
            },
        )
