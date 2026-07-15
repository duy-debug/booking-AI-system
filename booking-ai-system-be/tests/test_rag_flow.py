# Integration tests cho RAG module — KB seed + search + chat API
# Tối ưu: seed 1 lần cho cả session, mock Groq để test logic

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.rag.vector_store import count_chunks


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session", autouse=True)
def seed_kb_once():
    from app.db.session import SessionLocal

    db = SessionLocal()
    if count_chunks(db) == 0:
        from app.rag.ingestion import seed_all_docs

        seed_all_docs(db)
    db.close()
    yield


def test_kb_stats(client: TestClient):
    r = client.get("/api/kb/stats")
    assert r.status_code == 200
    assert r.json()["total_chunks"] > 0


def test_kb_seed_without_auth(client: TestClient):
    r = client.post("/api/kb/seed")
    assert r.status_code == 401


def test_kb_seed_with_auth_succeeds(client: TestClient):
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    token = r.json()["data"]["access_token"]
    r = client.post("/api/kb/seed", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["stats"]["total_chunks"] > 0


@patch("app.rag.chain._get_groq_client")
def test_chat_valid(mock_get_client, client: TestClient):
    mock_client_instance = mock_get_client.return_value
    mock_response = mock_client_instance.chat.completions.create.return_value
    mock_response.choices = [
        type("obj", (), {"message": type("obj", (), {"content": "Chúng tôi có massage Thái, massage dầu."})()})()
    ]
    r = client.post("/api/chat", json={"query": "có dịch vụ gì?"})
    assert r.status_code == 200
    assert r.json()["answer"] == "Chúng tôi có massage Thái, massage dầu."


@patch("app.rag.chain._get_groq_client")
def test_chat_streaming(mock_get_client, client: TestClient):
    mock_client_instance = mock_get_client.return_value

    class MockDelta:
        def __init__(self, content):
            self.content = content

    class MockChoice:
        def __init__(self, content):
            self.delta = MockDelta(content)

    class MockChunk:
        def __init__(self, content):
            self.choices = [MockChoice(content)]

    mock_client_instance.chat.completions.create.return_value = [
        MockChunk("Nội "),
        MockChunk("dung "),
        MockChunk("trả lời."),
    ]
    r = client.post("/api/chat", json={"query": "xin chào", "stream": True})
    assert r.status_code == 200
    assert "text/event-stream" in r.headers["content-type"]


@patch("app.rag.chain._get_groq_client")
def test_chat_uses_context(mock_get_client, client: TestClient):
    mock_client_instance = mock_get_client.return_value
    mock_response = mock_client_instance.chat.completions.create.return_value
    mock_response.choices = [
        type("obj", (), {"message": type("obj", (), {"content": "OK"})()})()
    ]
    r = client.post("/api/chat", json={"query": "quy trình đặt booking thế nào?"})
    assert r.status_code == 200
    call_kwargs = mock_client_instance.chat.completions.create.call_args
    assert call_kwargs is not None
    messages = call_kwargs[1].get("messages", [])
    system_msg = next(m for m in messages if m["role"] == "system")
    assert len(system_msg["content"]) > 500
