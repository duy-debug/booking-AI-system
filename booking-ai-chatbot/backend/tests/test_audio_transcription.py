from unittest.mock import patch

from fastapi.testclient import TestClient


def test_transcribe_vietnamese_audio(client: TestClient) -> None:
    with patch("app.api.audio._transcribe", return_value="Tôi muốn đặt lịch ngày mai."):
        response = client.post(
            "/api/v1/audio/transcriptions",
            files={"file": ("recording.webm", b"audio-content", "audio/webm")},
        )

    assert response.status_code == 200
    assert response.json() == {"text": "Tôi muốn đặt lịch ngày mai."}


def test_rejects_unsupported_audio_type(client: TestClient) -> None:
    response = client.post(
        "/api/v1/audio/transcriptions",
        files={"file": ("recording.txt", b"not-audio", "text/plain")},
    )

    assert response.status_code == 415
    assert response.json()["code"] == "UNSUPPORTED_AUDIO_TYPE"


def test_rejects_empty_audio(client: TestClient) -> None:
    response = client.post(
        "/api/v1/audio/transcriptions",
        files={"file": ("recording.webm", b"", "audio/webm")},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "EMPTY_AUDIO"


def test_rejects_common_silence_hallucination(client: TestClient) -> None:
    with patch(
        "app.api.audio._transcribe",
        return_value="Hãy subscribe để không bỏ lỡ những video hấp dẫn.",
    ):
        response = client.post(
            "/api/v1/audio/transcriptions",
            files={"file": ("recording.webm", b"background-noise", "audio/webm")},
        )

    assert response.status_code == 422
    assert response.json()["code"] == "SPEECH_NOT_RECOGNIZED"
