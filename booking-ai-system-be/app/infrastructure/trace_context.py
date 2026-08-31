"""Distributed trace ContextVar and POS ASGI middleware."""

import logging
import re
from contextvars import ContextVar, Token
from dataclasses import dataclass
from http import HTTPStatus
from time import perf_counter
from typing import Any
from urllib.parse import parse_qsl
from uuid import uuid4

from app.infrastructure.logging_config import log_event

_SAFE_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


# TraceContext giữ định danh xuyên suốt request để POS log khớp được với chatbot hoặc POS UI.
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


# Lấy trace context hiện tại; nếu request chưa bind thì trả context rỗng an toàn cho logging.
def current_trace_context() -> TraceContext:
    return _current.get() or TraceContext()


# Bind trace context vào ContextVar để các async task trong cùng request dùng chung metadata.
def bind_trace_context(context: TraceContext) -> Token[TraceContext | None]:
    return _current.set(context)


# Khôi phục context cũ sau request để trace không bị rò sang request kế tiếp.
def reset_trace_context(token: Token[TraceContext | None]) -> None:
    _current.reset(token)


# Middleware gắn trace id/request id vào toàn bộ vòng đời HTTP request của POS backend.
class TraceMiddleware:
    """Keep upstream trace identity for the full POS HTTP lifecycle."""

    # Lưu ASGI app kế tiếp trong chain middleware.
    def __init__(self, app: Any) -> None:
        self.app = app

    # Bao quanh request HTTP để bind trace, thêm response header và log kết quả cuối cùng.
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
        log_event(
            logging.DEBUG,
            "POSMiddleware",
            "pos_request_received",
            method=scope.get("method"),
            path=str(scope.get("path", "")),
        )

        # Intercept response start để trả trace id cho caller, giúp đối chiếu log hai hệ thống.
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
            self._log_completed_request(
                scope=scope,
                status_code=status_code,
                duration_ms=round((perf_counter() - started) * 1000),
                context=context,
            )
        except Exception as error:
            normalized_path = _normalized_path(scope)
            endpoint = _endpoint_name(scope)
            source = _request_source(context)
            message = (
                f"[source={source}]"
                + (f"[turn={context.turn_id}]" if context.turn_id is not None else "")
                + f"[POS] {endpoint}\n"
                f"{scope.get('method')} {normalized_path}\n"
                f"→ 500 INTERNAL SERVER ERROR | "
                f"{round((perf_counter() - started) * 1000)}ms | "
                f"unexpected_exception | error_code={type(error).__name__}"
            )
            log_event(
                logging.ERROR,
                "POSMiddleware",
                "pos_request_failed",
                message=message,
                source=source,
                method=scope.get("method"),
                path=normalized_path,
                endpoint=endpoint,
                status_code=500,
                exception_type=type(error).__name__,
                duration_ms=round((perf_counter() - started) * 1000),
                exc_info=True,
            )
            raise
        finally:
            # Luôn reset context để request sau không kế thừa nhầm trace/session/turn hiện tại.
            reset_trace_context(token)

    # Ghi log request thành công hoặc lỗi nghiệp vụ với status, endpoint, params và duration.
    def _log_completed_request(
        self,
        *,
        scope: dict[str, Any],
        status_code: int,
        duration_ms: int,
        context: TraceContext,
    ) -> None:
        normalized_path = _normalized_path(scope)
        endpoint = _endpoint_name(scope)
        params = _important_params(scope)
        source = _request_source(context)
        error_code, status_hint = _error_metadata(scope)
        status_label = _status_label(status_code)
        lines = [
            f"[source={source}]"
            + (f"[turn={context.turn_id}]" if context.turn_id is not None else "")
            + f"[POS] {endpoint}",
            f"{scope.get('method')} {normalized_path}",
        ]
        if params:
            lines.append(f"params={params}")
        result_line = f"→ {status_code} {status_label} | {duration_ms}ms"
        if status_code >= 400:
            result_line += f" | {status_hint}"
            if error_code is not None:
                result_line += f" | error_code={error_code}"
        lines.append(result_line)
        message = "\n".join(lines)
        level = logging.INFO
        event = "pos_request_completed"
        if 400 <= status_code < 500:
            level = logging.WARNING
            event = "pos_request_failed"
        elif status_code >= 500:
            level = logging.ERROR
            event = "pos_request_failed"
        log_event(
            level,
            "POSMiddleware",
            event,
            message=message,
            source=source,
            method=scope.get("method"),
            path=normalized_path,
            endpoint=endpoint,
            status_code=status_code,
            params=params or None,
            duration_ms=duration_ms,
            error_code=error_code,
        )


# Chỉ chấp nhận trace/request/session id có ký tự an toàn, còn lại thay bằng default.
def _valid(value: str | None, default: str) -> str:
    normalized = value.strip() if value else ""
    return normalized if _SAFE_ID.fullmatch(normalized) else default


# Parse turn id từ header chatbot; POS UI không có turn id nên sẽ được phân loại riêng.
def _turn(value: str | None) -> int | None:
    if value is None or not value.isdigit():
        return None
    parsed = int(value)
    return parsed if parsed > 0 else None


# Map endpoint kỹ thuật thành tên operation nghiệp vụ để log dễ đọc hơn.
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


# Ưu tiên path template của FastAPI để log không bị nhiễu bởi UUID/id cụ thể.
def _normalized_path(scope: dict[str, Any]) -> str:
    route = scope.get("route")
    path_format = getattr(route, "path_format", None)
    if isinstance(path_format, str) and path_format:
        return path_format
    return str(scope.get("path", ""))


# Lấy tên endpoint handler để developer trace từ log về đúng router function.
def _endpoint_name(scope: dict[str, Any]) -> str:
    endpoint = scope.get("endpoint")
    module = getattr(endpoint, "__module__", "")
    function = getattr(endpoint, "__name__", "")
    if module and function:
        return f"{module.rsplit('.', maxsplit=1)[-1]}.{function}()"
    if function:
        return f"{function}()"
    return "unknown_endpoint()"


# Ghi lại query params quan trọng giúp debug request POS mà không cần log toàn bộ body.
def _important_params(scope: dict[str, Any]) -> dict[str, str]:
    query_string = scope.get("query_string", b"")
    if not isinstance(query_string, bytes) or not query_string:
        return {}
    return dict(parse_qsl(query_string.decode("latin-1"), keep_blank_values=False))


# Chuẩn hóa metadata lỗi do router/service gắn vào scope để log phân biệt validation và business error.
def _error_metadata(scope: dict[str, Any]) -> tuple[str | None, str]:
    error = scope.get("pos_error")
    if not isinstance(error, dict):
        return None, "request_failed"
    code = error.get("error_code")
    safe_code = code if isinstance(code, str) and code else None
    if error.get("validation") is True:
        return safe_code, "validation_failed"
    return safe_code, "business_failed"


# Chuyển HTTP status code thành nhãn dễ đọc trong log console.
def _status_label(status_code: int) -> str:
    try:
        return HTTPStatus(status_code).phrase.upper()
    except ValueError:
        return "UNKNOWN"


# Phân biệt request đến từ chatbot hay POS UI dựa trên turn id được truyền qua header.
def _request_source(context: TraceContext) -> str:
    return "chatbot" if context.turn_id is not None else "pos_ui"
