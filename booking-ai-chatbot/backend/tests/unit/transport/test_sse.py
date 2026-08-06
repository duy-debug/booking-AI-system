"""Unit tests for SSE framing and chat event generation."""

import asyncio
import json
from collections.abc import Mapping
from typing import cast

import pytest

import app.transport.chat_api as chat_api
from app.dependencies import ApplicationContainer
from app.dialog.dialog_controller import DialogTurnStatus
from app.dialog.instruction_builder import DialogResponse
from app.domain.booking_context import BookingContext
from app.domain.booking_state import BookingState
from app.transport.chat_api import _stream_chat_events
from app.transport.schemas import ChatRequest
from app.transport.sse import (
    InvalidSSEEventError,
    SSESerializationError,
    encode_sse_event,
)


def decode_frame(frame: str) -> tuple[str, dict[str, object]]:
    lines = frame.removesuffix("\n\n").split("\n")
    event = lines[0].removeprefix("event: ")
    data = json.loads(lines[1].removeprefix("data: "))
    assert isinstance(data, dict)
    return event, data


def request() -> ChatRequest:
    return ChatRequest(
        conversation_id="conversation-a",
        message="Tôi muốn đặt lịch",
    )


def response() -> DialogResponse:
    return DialogResponse(
        text="Vui lòng chọn cửa hàng.",
        instruction_template="ask_shop",
        state=BookingState.SELECTING_SHOP,
        status=DialogTurnStatus.SUCCESS,
        quick_replies=("Shibuya",),
        metadata={"can_retry": False},
    )


def test_encoder_outputs_compact_utf8_json_and_terminal_newlines() -> None:
    frame = encode_sse_event(
        event="message",
        data={"text": "Vui lòng chọn cửa hàng.", "ok": True},
    )

    assert frame == ('event: message\ndata: {"text":"Vui lòng chọn cửa hàng.","ok":true}\n\n')
    assert "\\u" not in frame
    assert frame.endswith("\n\n")
    assert "True" not in frame


def test_encoder_supports_empty_and_nested_json_objects() -> None:
    empty = encode_sse_event(event="started", data={})
    nested = encode_sse_event(
        event="message",
        data={"metadata": {"can_retry": True, "count": 2}},
    )

    assert decode_frame(empty) == ("started", {})
    assert decode_frame(nested) == (
        "message",
        {"metadata": {"can_retry": True, "count": 2}},
    )


@pytest.mark.parametrize("event", ["", "Message", "bad event", "bad\nname", ":bad"])
def test_encoder_rejects_invalid_event_names(event: str) -> None:
    with pytest.raises(InvalidSSEEventError):
        encode_sse_event(event=event, data={})


def test_encoder_rejects_non_mapping_data() -> None:
    with pytest.raises(InvalidSSEEventError):
        encode_sse_event(
            event="message",
            data=cast(Mapping[str, object], ["not", "an", "object"]),
        )


def test_encoder_does_not_silently_serialize_domain_objects() -> None:
    with pytest.raises(SSESerializationError):
        encode_sse_event(
            event="message",
            data={"context": BookingContext("conversation-a")},
        )


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_encoder_rejects_non_finite_numbers(value: float) -> None:
    with pytest.raises(SSESerializationError):
        encode_sse_event(event="message", data={"score": value})


def test_json_escaping_prevents_newlines_from_breaking_the_sse_frame() -> None:
    frame = encode_sse_event(
        event="message",
        data={"text": "line one\nline two"},
    )

    assert frame.count("\n") == 3
    assert "line one\\nline two" in frame
    assert decode_frame(frame)[1] == {"text": "line one\nline two"}


@pytest.mark.asyncio
async def test_stream_generator_emits_started_message_completed_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    async def process_message(
        *,
        request: ChatRequest,
        container: ApplicationContainer,
    ) -> DialogResponse:
        nonlocal calls
        calls += 1
        return response()

    monkeypatch.setattr(chat_api, "_process_chat_message", process_message)

    frames = [
        frame
        async for frame in _stream_chat_events(
            request=request(),
            container=cast(ApplicationContainer, object()),
        )
    ]
    events = [decode_frame(frame) for frame in frames]

    assert calls == 1
    assert [event for event, _ in events] == ["started", "message", "completed"]
    assert events[0][1] == {"conversation_id": "conversation-a"}
    assert events[1][1]["text"] == "Vui lòng chọn cửa hàng."
    assert events[2][1] == {
        "conversation_id": "conversation-a",
        "stream_status": "completed",
        "dialog_status": "success",
    }


@pytest.mark.asyncio
async def test_stream_generator_emits_safe_error_without_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_processing(
        *,
        request: ChatRequest,
        container: ApplicationContainer,
    ) -> DialogResponse:
        raise RuntimeError("private POS response and stack detail")

    monkeypatch.setattr(chat_api, "_process_chat_message", fail_processing)

    frames = [
        frame
        async for frame in _stream_chat_events(
            request=request(),
            container=cast(ApplicationContainer, object()),
        )
    ]
    events = [decode_frame(frame) for frame in frames]

    assert [event for event, _ in events] == ["started", "error"]
    assert events[1][1]["code"] == "chat_processing_failed"
    assert "private POS" not in "".join(frames)


@pytest.mark.asyncio
async def test_stream_generator_propagates_client_cancellation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def cancel_processing(
        *,
        request: ChatRequest,
        container: ApplicationContainer,
    ) -> DialogResponse:
        raise asyncio.CancelledError

    monkeypatch.setattr(chat_api, "_process_chat_message", cancel_processing)
    stream = _stream_chat_events(
        request=request(),
        container=cast(ApplicationContainer, object()),
    )

    assert decode_frame(await anext(stream))[0] == "started"
    with pytest.raises(asyncio.CancelledError):
        await anext(stream)
