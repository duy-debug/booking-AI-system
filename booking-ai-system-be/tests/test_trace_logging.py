"""POS distributed tracing and canonical request logging tests."""

import asyncio
import json
import logging
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.infrastructure.logging_config import JsonFormatter, configure_logging
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


@pytest.mark.asyncio
async def test_pos_success_request_emits_one_canonical_info_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    application = FastAPI()
    application.add_middleware(TraceMiddleware)

    @application.get("/api/shops/{shop_id}/courses")
    async def list_courses(
        shop_id: str,
        course_type: str = Query(...),
    ) -> dict[str, object]:
        return {"shop_id": shop_id, "course_type": course_type}

    caplog.set_level(logging.DEBUG)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application),
        base_url="http://test",
    ) as client:
        response = await client.get(
            f"/api/shops/{uuid4()}/courses",
            params={"course_type": "addon"},
            headers={"X-Turn-ID": "8"},
        )

    assert response.status_code == 200
    pos_info = [
        record
        for record in caplog.records
        if record.name == "app.POSMiddleware" and record.levelno == logging.INFO
    ]
    assert len(pos_info) == 1
    record = pos_info[0]
    assert getattr(record, "event", None) == "pos_request_completed"
    assert getattr(record, "path", None) == "/api/shops/{shop_id}/courses"
    assert getattr(record, "endpoint", None) == "test_trace_logging.list_courses()"
    assert getattr(record, "source", None) == "chatbot"
    assert getattr(record, "params", None) == {"course_type": "addon"}
    assert "[source=chatbot][turn=8][POS] test_trace_logging.list_courses()" in record.getMessage()
    assert "GET /api/shops/{shop_id}/courses" in record.getMessage()
    assert "params={'course_type': 'addon'}" in record.getMessage()
    assert "→ 200 OK |" in record.getMessage()
    assert not any(
        item.levelno == logging.INFO and getattr(item, "event", None) == "pos_request_received"
        for item in caplog.records
    )


@pytest.mark.asyncio
async def test_pos_validation_failure_emits_one_canonical_warning_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    application = FastAPI()
    application.add_middleware(TraceMiddleware)

    @application.exception_handler(RequestValidationError)
    async def validation_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        request.scope["pos_error"] = {
            "error_code": "VALIDATION_ERROR",
            "status_code": 422,
            "invalid_fields": [".".join(str(part) for part in error["loc"]) for error in exc.errors()],
            "validation": True,
        }
        return JSONResponse(status_code=422, content={"code": "VALIDATION_ERROR"})

    @application.get("/api/shops/{shop_id}/available-slots")
    async def list_available_slots(
        shop_id: str,
        booking_date: str = Query(...),
    ) -> dict[str, object]:
        return {"shop_id": shop_id, "booking_date": booking_date}

    caplog.set_level(logging.DEBUG)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application),
        base_url="http://test",
    ) as client:
        response = await client.get(f"/api/shops/{uuid4()}/available-slots")

    assert response.status_code == 422
    pos_warning = [
        record
        for record in caplog.records
        if record.name == "app.POSMiddleware" and record.levelno == logging.WARNING
    ]
    assert len(pos_warning) == 1
    record = pos_warning[0]
    assert getattr(record, "event", None) == "pos_request_failed"
    assert getattr(record, "path", None) == "/api/shops/{shop_id}/available-slots"
    assert getattr(record, "endpoint", None) == "test_trace_logging.list_available_slots()"
    assert getattr(record, "source", None) == "pos_ui"
    assert getattr(record, "error_code", None) == "VALIDATION_ERROR"
    assert "[source=pos_ui][POS] test_trace_logging.list_available_slots()" in record.getMessage()
    assert "→ 422 UNPROCESSABLE ENTITY |" in record.getMessage()
    assert "validation_failed" in record.getMessage()
    assert "error_code=VALIDATION_ERROR" in record.getMessage()


def test_configure_logging_disables_uvicorn_access_info_logs() -> None:
    configure_logging(level="INFO", log_format="console")
    access_logger = logging.getLogger("uvicorn.access")

    assert access_logger.level == logging.WARNING
    assert access_logger.propagate is False
