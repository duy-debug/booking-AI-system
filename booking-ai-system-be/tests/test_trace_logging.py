"""POS distributed tracing and safe structured logging tests."""

import asyncio
import json
import logging

import httpx
import pytest
from fastapi import FastAPI

from app.infrastructure.logging_config import JsonFormatter
from app.infrastructure.trace_context import (
    TraceContext,
    TraceMiddleware,
    bind_trace_context,
    current_trace_context,
    reset_trace_context,
)
from app.utils.sensitive_data import mask_phone, redact_headers


@pytest.mark.asyncio
async def test_pos_preserves_upstream_trace_and_returns_it() -> None:
    application = FastAPI()
    application.add_middleware(TraceMiddleware)

    @application.get("/probe")
    async def probe() -> dict[str, object]:
        context = current_trace_context()
        return {
            "trace_id": context.trace_id,
            "request_id": context.request_id,
            "session_id": context.session_id,
            "turn_id": context.turn_id,
        }

    headers = {
        "X-Trace-ID": "trace-chatbot",
        "X-Request-ID": "req-chatbot",
        "X-Session-ID": "sess-chatbot",
        "X-Turn-ID": "9",
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application),
        base_url="http://test",
    ) as client:
        response = await client.get("/probe", headers=headers)

    assert response.headers["x-trace-id"] == "trace-chatbot"
    assert response.json() == {
        "trace_id": "trace-chatbot",
        "request_id": "req-chatbot",
        "session_id": "sess-chatbot",
        "turn_id": 9,
    }


@pytest.mark.asyncio
async def test_pos_context_does_not_leak_across_tasks() -> None:
    async def observe(value: str) -> str:
        token = bind_trace_context(TraceContext(trace_id=value))
        try:
            await asyncio.sleep(0)
            return current_trace_context().trace_id
        finally:
            reset_trace_context(token)

    assert await asyncio.gather(observe("trace-a"), observe("trace-b")) == [
        "trace-a",
        "trace-b",
    ]
    assert current_trace_context().trace_id == "-"


def test_pos_json_logging_and_redaction_are_safe() -> None:
    record = logging.LogRecord(
        "app.test",
        logging.INFO,
        __file__,
        1,
        "phone 0912345678",
        (),
        None,
    )
    token = bind_trace_context(TraceContext(trace_id="trace-json"))
    try:
        payload = json.loads(JsonFormatter().format(record))
    finally:
        reset_trace_context(token)

    assert payload["service"] == "pos-backend"
    assert payload["trace_id"] == "trace-json"
    assert "0912345678" not in payload["message"]
    assert mask_phone("0912345678") in payload["message"]
    assert redact_headers({"Authorization": "Bearer secret"})["Authorization"] == "***"
