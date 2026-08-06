"""Distributed trace ContextVar and POS ASGI middleware."""

import logging
import re
from contextvars import ContextVar, Token
from dataclasses import dataclass
from time import perf_counter
from typing import Any
from uuid import uuid4

from app.infrastructure.logging_config import log_event

_SAFE_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


@dataclass(frozen=True, slots=True)
class TraceContext:
    trace_id: str = "-"
    request_id: str = "-"
    session_id: str = "-"
    turn_id: int | None = None


_current: ContextVar[TraceContext | None] = ContextVar(
    "pos_trace_context",
    default=None,
)


def current_trace_context() -> TraceContext:
    return _current.get() or TraceContext()


def bind_trace_context(context: TraceContext) -> Token[TraceContext | None]:
    return _current.set(context)


def reset_trace_context(token: Token[TraceContext | None]) -> None:
    _current.reset(token)


class TraceMiddleware:
    """Keep upstream trace identity for the full POS HTTP lifecycle."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        headers = {
            key.decode("latin-1").casefold(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        context = TraceContext(
            trace_id=_valid(headers.get("x-trace-id"), f"trace-{uuid4().hex}"),
            request_id=_valid(headers.get("x-request-id"), f"req-{uuid4().hex}"),
            session_id=_valid(headers.get("x-session-id"), "-"),
            turn_id=_turn(headers.get("x-turn-id")),
        )
        token = bind_trace_context(context)
        started = perf_counter()
        status_code = 500
        path = str(scope.get("path", ""))
        operation = _operation(scope)
        log_event(
            logging.INFO,
            "POSMiddleware",
            "pos_request_received",
            method=scope.get("method"),
            path=path,
            operation=operation,
        )

        async def send_with_trace(message: dict[str, Any]) -> None:
            nonlocal status_code
            if message.get("type") == "http.response.start":
                status_code = int(message.get("status", 500))
                response_headers = list(message.get("headers", []))
                response_headers.extend(
                    [
                        (b"x-trace-id", context.trace_id.encode("ascii")),
                        (b"x-request-id", context.request_id.encode("ascii")),
                    ]
                )
                message["headers"] = response_headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_trace)
            log_event(
                logging.INFO,
                "POSMiddleware",
                "pos_request_completed",
                operation=operation,
                path=path,
                status_code=status_code,
                duration_ms=round((perf_counter() - started) * 1000),
            )
        except Exception as error:
            log_event(
                logging.ERROR,
                "POSMiddleware",
                "pos_request_failed",
                operation=operation,
                path=path,
                status_code=500,
                exception_type=type(error).__name__,
                duration_ms=round((perf_counter() - started) * 1000),
                exc_info=True,
            )
            raise
        finally:
            reset_trace_context(token)


def _valid(value: str | None, default: str) -> str:
    normalized = value.strip() if value else ""
    return normalized if _SAFE_ID.fullmatch(normalized) else default


def _turn(value: str | None) -> int | None:
    if value is None or not value.isdigit():
        return None
    parsed = int(value)
    return parsed if parsed > 0 else None


def _operation(scope: dict[str, Any]) -> str:
    path = str(scope.get("path", ""))
    method = str(scope.get("method", ""))
    if path == "/api/shops":
        return "search_shops"
    if path.endswith("/courses"):
        return "search_services"
    if path.endswith("/available-slots"):
        return "get_available_slots"
    if path.endswith("/available-therapists"):
        return "search_available_therapists"
    if path == "/api/booking-eligibility-checks":
        return "verify_customer"
    if path == "/api/bookings" and method == "POST":
        return "create_booking"
    return "http_request"
