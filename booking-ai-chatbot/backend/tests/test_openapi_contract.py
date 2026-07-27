from fastapi.testclient import TestClient


def test_v1_chat_is_the_documented_contract(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    assert "/api/v1/chat" in schema["paths"]
    assert "/api/v1/chat/stream" in schema["paths"]
    assert "/api/chat" not in schema["paths"]


def test_chat_response_ui_is_discriminated_union(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    response = schema["components"]["schemas"]["ChatResponse"]
    ui_schema = response["properties"]["ui"]["anyOf"][0]
    assert ui_schema["discriminator"]["propertyName"] == "type"
    mapping = ui_schema["discriminator"]["mapping"]
    assert "booking_cancel_summary" in mapping
    assert "booking_update_summary" in mapping


def test_legacy_chat_remains_backward_compatible(client: TestClient) -> None:
    response = client.post("/api/chat", json={"conversation_id": "c"})
    assert response.status_code == 422


def test_v1_chat_validates_same_contract(client: TestClient) -> None:
    response = client.post("/api/v1/chat", json={"conversation_id": "c"})
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
