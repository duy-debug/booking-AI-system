import json
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.api.chat import get_orchestrator
from app.core.exceptions import AppError
from app.core.token_stream import get_token_emitter
from app.main import app


def _events(response) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    current_event = ""
    for line in response.iter_lines():
        if line.startswith("event: "):
            current_event = line.removeprefix("event: ")
        elif line.startswith("data: "):
            events.append((current_event, json.loads(line.removeprefix("data: "))))
    return events


def test_chat_stream_emits_typed_events(client: TestClient) -> None:
    orchestrator = AsyncMock()
    orchestrator.handle.return_value = {
        "answer": "Xin chào bạn",
        "intent": "general",
        "conversation_id": "conversation-1",
        "ui": {
            "type": "text",
            "options": [],
            "data": {"source": "test"},
        },
    }
    app.dependency_overrides[get_orchestrator] = lambda: orchestrator
    try:
        with client.stream(
            "POST",
            "/api/v1/chat/stream",
            json={"query": "hello", "conversation_id": "conversation-1"},
        ) as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            events = _events(response)
    finally:
        app.dependency_overrides.pop(get_orchestrator, None)

    names = [name for name, _ in events]
    assert names[0] == "start"
    assert names[-1] == "done"
    assert "token" in names
    assert "ui" in names
    assert "".join(data["delta"] for name, data in events if name == "token") == "Xin chào bạn"
    assert events[-1][1]["ui"]["type"] == "text"


def test_chat_stream_maps_application_error_to_error_event(client: TestClient) -> None:
    orchestrator = AsyncMock()
    orchestrator.handle.side_effect = AppError(
        503,
        code="DEPENDENCY_UNAVAILABLE",
        detail="Dịch vụ phụ thuộc không khả dụng.",
    )
    app.dependency_overrides[get_orchestrator] = lambda: orchestrator
    try:
        with client.stream(
            "POST",
            "/api/v1/chat/stream",
            json={"query": "hello", "conversation_id": "conversation-1"},
        ) as response:
            events = _events(response)
    finally:
        app.dependency_overrides.pop(get_orchestrator, None)

    assert [name for name, _ in events] == ["start", "error"]
    assert events[-1][1]["code"] == "DEPENDENCY_UNAVAILABLE"


def test_chat_stream_forwards_upstream_provider_tokens_without_duplicate(
    client: TestClient,
) -> None:
    orchestrator = AsyncMock()

    async def streamed_handle(**_kwargs):
        emitter = get_token_emitter()
        assert emitter is not None
        emitter("Xin ")
        emitter("chào")
        return {
            "answer": "Xin chào",
            "intent": "general",
            "conversation_id": "conversation-1",
        }

    orchestrator.handle.side_effect = streamed_handle
    app.dependency_overrides[get_orchestrator] = lambda: orchestrator
    try:
        with client.stream(
            "POST",
            "/api/v1/chat/stream",
            json={"query": "hello", "conversation_id": "conversation-1"},
        ) as response:
            events = _events(response)
    finally:
        app.dependency_overrides.pop(get_orchestrator, None)

    tokens = [data["delta"] for name, data in events if name == "token"]
    assert tokens == ["Xin ", "chào"]
    assert events[-1][0] == "done"
