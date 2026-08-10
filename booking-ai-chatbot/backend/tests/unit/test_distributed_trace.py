"""Distributed trace identity and POS propagation tests."""

import asyncio
import json
import logging

import httpx
import pytest
from fastapi import FastAPI

from app.infrastructure.context_store import (
    JsonFormatter,
    TraceMiddleware,
    bind_trace_context,
    current_trace_context,
    reset_trace_context,
)
from app.infrastructure.pos_api_client import PosApiClient


@pytest.mark.asyncio
async def test_trace_middleware_returns_trace_and_request_headers() -> None:
    application = FastAPI()
    application.add_middleware(TraceMiddleware, service="booking-chatbot")

    @application.get("/probe")
    async def probe() -> dict[str, str]:
        context = current_trace_context()
        return {"trace_id": context.trace_id, "request_id": context.request_id}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application),
        base_url="http://test",
    ) as client:
        response = await client.get("/probe", headers={"X-Trace-ID": "trace-upstream"})

    assert response.status_code == 200
    assert response.headers["x-trace-id"] == "trace-upstream"
    assert response.headers["x-request-id"].startswith("req-")
    assert response.json()["trace_id"] == "trace-upstream"


@pytest.mark.asyncio
async def test_pos_client_propagates_all_trace_headers_without_logging_payload() -> None:
    captured: list[httpx.Request] = []

    def responder(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"data": [], "meta": {"total": 0}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(responder))
    gateway = PosApiClient(client=client, base_url="http://pos.test")
    token = bind_trace_context(
        trace_id="trace-1",
        request_id="req-1",
        session_id="sess-1",
        turn_id=7,
    )
    try:
        await gateway.search_shops()
    finally:
        reset_trace_context(token)
        await client.aclose()

    assert len(captured) == 1
    assert captured[0].headers["X-Trace-ID"] == "trace-1"
    assert captured[0].headers["X-Request-ID"] == "req-1"
    assert captured[0].headers["X-Session-ID"] == "sess-1"
    assert captured[0].headers["X-Turn-ID"] == "7"


@pytest.mark.asyncio
async def test_contextvars_do_not_leak_between_concurrent_tasks() -> None:
    async def observe(trace_id: str) -> str:
        token = bind_trace_context(trace_id=trace_id)
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


def test_json_log_has_mandatory_trace_fields() -> None:
    record = logging.LogRecord("app.test", logging.INFO, __file__, 1, "ok", (), None)
    token = bind_trace_context(trace_id="trace-json")
    try:
        payload = json.loads(JsonFormatter().format(record))
    finally:
        reset_trace_context(token)

    assert payload["service"] == "booking-chatbot"
    assert payload["component"] == "app.test"
    assert payload["event"] == "log_record"
    assert payload["trace_id"] == "trace-json"
