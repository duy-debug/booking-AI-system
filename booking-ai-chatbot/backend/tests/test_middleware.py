from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient


def test_correlation_id_is_returned(client: TestClient) -> None:
    correlation_id = str(uuid4())
    response = client.get("/health", headers={"X-Correlation-ID": correlation_id})
    assert response.headers["X-Correlation-ID"] == correlation_id


def test_invalid_correlation_id_is_replaced(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Correlation-ID": "unsafe"})
    assert response.headers["X-Correlation-ID"] != "unsafe"
    assert response.headers["X-Correlation-ID"]


def test_rate_limit_returns_problem_details(client: TestClient) -> None:
    store = AsyncMock()
    store.check_rate_limit.return_value = False
    with patch("app.core.middleware.get_conversation_store", return_value=store):
        response = client.post(
            "/api/v1/chat",
            json={"query": "xin chào", "conversation_id": "c"},
        )
    assert response.status_code == 429
    assert response.json()["code"] == "RATE_LIMIT_EXCEEDED"
