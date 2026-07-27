import os

import httpx
import pytest

BASE_URL = os.getenv("CHATBOT_E2E_URL")
pytestmark = pytest.mark.integration


@pytest.mark.skipif(not BASE_URL, reason="Set CHATBOT_E2E_URL to run live-stack tests")
def test_live_stack_is_ready_and_exposes_v1_contract() -> None:
    ready = httpx.get(f"{BASE_URL}/ready", timeout=20)
    assert ready.status_code == 200, ready.text
    schema = httpx.get(f"{BASE_URL}/openapi.json", timeout=20).json()
    assert "/api/v1/chat" in schema["paths"]


@pytest.mark.skipif(not BASE_URL, reason="Set CHATBOT_E2E_URL to run live-stack tests")
def test_live_chat_returns_versioned_typed_response() -> None:
    response = httpx.post(
        f"{BASE_URL}/api/v1/chat",
        json={"query": "xin chào"},
        timeout=30,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["contract_version"] == "1.0"
    assert body["conversation_id"]
    assert body["answer"]
