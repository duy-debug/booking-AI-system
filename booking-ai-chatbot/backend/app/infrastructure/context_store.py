# Cấu hình runtime và tiện ích context/trace dùng chung cho toàn bộ ứng dụng.
# ruff: noqa: E402
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


def _default_env_path() -> Path:
    return Path(__file__).resolve().parents[2] / ".env"


def load_runtime_environment(env_file: Path | None = None) -> Path:
    """
    Nạp file `.env` cục bộ của backend mà không ghi đè biến môi trường hệ thống.
    """
    resolved_path = (env_file or _default_env_path()).resolve()
    load_dotenv(dotenv_path=resolved_path, override=False)
    return resolved_path


def _default_booking_flow_path() -> Path:
    return Path(__file__).resolve().parents[1] / "dialog" / "booking_flow.json"


def _default_change_handlers_path() -> Path:
    return _default_booking_flow_path()


@dataclass(frozen=True, slots=True)
class Settings:
    """
    Chứa các giá trị cấu hình cần để ghép đầy đủ chatbot ở composition root.
    """

    pos_base_url: str
    pos_timeout_seconds: float = 10.0
    booking_flow_path: Path = field(default_factory=_default_booking_flow_path)
    change_handlers_path: Path = field(default_factory=_default_change_handlers_path)
    max_auto_transitions: int = 8
    llm_nlg_required: bool = False
    llm_nlu_min_confidence: float = 0.70
    llm_provider: str = "gemini"
    gemini_api_key: str | None = None
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    gemini_model: str = "gemini-3.5-flash-lite"
    gemini_fallback_model: str | None = None
    llm_max_retries: int = 0
    dialog_intent_tool_enabled: bool = True
    business_timezone: str = "Asia/Ho_Chi_Minh"
    embedding_model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_api_key: str | None = None
    qdrant_collection: str = "kb_chunks"
    knowledge_qdrant_enabled: bool = False
    rag_hybrid_score_threshold: float = 0.45


# Che dữ liệu nhạy cảm và rút gọn payload dùng cho logging/observability.

import re
from collections.abc import Mapping

_PHONE = re.compile(r"(?<!\d)\+?\d(?:[ -]?\d){8,14}(?!\d)")
_EMAIL = re.compile(r"\b([^\s@])[^\s@]*@([^\s@]+)\b")
_BEARER = re.compile(r"(?i)\bBearer\s+[^\s,;]+")
_UUID = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
_SECRET_KEYS = frozenset(
    {
        "authorization",
        "api_key",
        "access_token",
        "refresh_token",
        "password",
        "cookie",
        "secret",
    }
)


def mask_phone(value: str) -> str:
    """
    Che số điện thoại nhưng vẫn giữ một phần prefix/suffix để tiện đối chiếu log.
    """
    digits = "".join(character for character in value if character.isdigit())
    if len(digits) < 7:
        return "***"
    return f"{digits[:3]}***{digits[-4:]}"


def mask_email(value: str) -> str:
    """
    Che phần local của email trước khi đưa vào log hoặc metadata quan sát.
    """
    match = _EMAIL.fullmatch(value.strip())
    if match is None:
        return "***"
    return f"{match.group(1)}***@{match.group(2)}"


def redact_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """
    Loại bỏ credential khỏi headers nhưng vẫn giữ metadata trace an toàn.
    """
    return {
        key: "***" if _is_secret_key(key) else sanitize_text(value)
        for key, value in headers.items()
    }


def sanitize_dict(values: Mapping[str, object]) -> dict[str, object]:
    """
    Làm sạch đệ quy một mapping trước khi log mà không ép serialize object tùy ý.
    """
    return {str(key): sanitize_value(str(key), value) for key, value in values.items()}


def sanitize_value(key: str, value: object) -> object:
    """
    Làm sạch một giá trị structured dựa trên tên field nghiệp vụ của nó.
    """
    normalized = key.casefold().replace("-", "_")
    if _is_secret_key(normalized) or "idempotency" in normalized:
        return "***"
    if "phone" in normalized:
        return mask_phone(str(value)) if value is not None else None
    if "email" in normalized:
        return mask_email(str(value)) if value is not None else None
    if isinstance(value, str):
        return sanitize_text(value)
    if isinstance(value, Mapping):
        return sanitize_dict(value)
    if isinstance(value, list | tuple | set | frozenset):
        return [sanitize_value(key, item) for item in value]
    if value is None or isinstance(value, bool | int | float):
        return value
    return str(value)


def sanitize_text(value: str) -> str:
    """
    Che token, phone, email trong text tự do trước khi text đi vào log.
    """
    protected: list[str] = []
    sanitized = _UUID.sub(
        lambda match: _protect(match.group(0), protected),
        value,
    )
    sanitized = _BEARER.sub("Bearer ***", sanitized)
    sanitized = _PHONE.sub(lambda match: mask_phone(match.group(0)), sanitized)
    sanitized = _EMAIL.sub(
        lambda match: f"{match.group(1)}***@{match.group(2)}",
        sanitized,
    )
    return _restore(sanitized, protected)


def sanitize_exception_data(error: BaseException) -> dict[str, str]:
    """
    Trả về metadata exception an toàn mà không lộ raw payload từ provider ngoài.
    """
    return {
        "exception_type": type(error).__name__,
        "exception_message": sanitize_text(str(error)),
    }


def _is_secret_key(key: str) -> bool:
    normalized = key.casefold().replace("-", "_")
    return normalized in _SECRET_KEYS or any(
        part in normalized for part in ("api_key", "token", "password", "secret")
    )


def _protect(value: str, protected: list[str]) -> str:
    protected.append(value)
    return f"\x00UUID{len(protected) - 1}\x00"


def _restore(value: str, protected: list[str]) -> str:
    for index, original in enumerate(protected):
        value = value.replace(f"\x00UUID{index}\x00", original)
    return value


# Quản lý trace context an toàn cho async và propagate header qua FastAPI/ASGI.

import logging
import re
from contextvars import ContextVar, Token
from dataclasses import dataclass
from time import perf_counter
from typing import Any
from uuid import uuid4

_SAFE_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


@dataclass(frozen=True, slots=True)
class TraceContext:
    trace_id: str = "-"
    request_id: str = "-"
    session_id: str = "-"
    turn_id: int | None = None


@dataclass(slots=True)
class TurnMetrics:
    intent: str | None = None
    handler: str | None = None
    outcome: str | None = None
    llm_calls: int = 0
    llm_input_tokens: int = 0
    llm_output_tokens: int = 0
    pos_calls: int = 0
    qdrant_calls: int = 0
    nlu_duration_ms: int = 0
    entity_resolution_ms: int = 0
    handler_duration_ms: int = 0
    nlg_duration_ms: int = 0

    def snapshot(self) -> "TurnMetrics":
        return TurnMetrics(
            intent=self.intent,
            handler=self.handler,
            outcome=self.outcome,
            llm_calls=self.llm_calls,
            llm_input_tokens=self.llm_input_tokens,
            llm_output_tokens=self.llm_output_tokens,
            pos_calls=self.pos_calls,
            qdrant_calls=self.qdrant_calls,
            nlu_duration_ms=self.nlu_duration_ms,
            entity_resolution_ms=self.entity_resolution_ms,
            handler_duration_ms=self.handler_duration_ms,
            nlg_duration_ms=self.nlg_duration_ms,
        )


_current: ContextVar[TraceContext | None] = ContextVar("trace_context", default=None)
_turn_metrics: ContextVar[TurnMetrics | None] = ContextVar("turn_metrics", default=None)
_completed_turn_metrics: ContextVar[TurnMetrics | None] = ContextVar(
    "completed_turn_metrics",
    default=None,
)


def current_trace_context() -> TraceContext:
    """
    Trả trace context hiện tại; nếu chưa bind thì dùng giá trị mặc định an toàn.
    """
    return _current.get() or TraceContext()


def bind_trace_context(
    *,
    trace_id: str | None = None,
    request_id: str | None = None,
    session_id: str | None = None,
    turn_id: int | None = None,
) -> Token[TraceContext | None]:
    # Bind trace fields mới nhưng vẫn kế thừa field cha nếu caller không truyền vào.
    parent = current_trace_context()
    return _current.set(
        TraceContext(
            trace_id=_validated_or_default(trace_id, parent.trace_id),
            request_id=_validated_or_default(request_id, parent.request_id),
            session_id=_validated_or_default(session_id, parent.session_id),
            turn_id=turn_id if turn_id is not None else parent.turn_id,
        )
    )


def reset_trace_context(token: Token[TraceContext | None]) -> None:
    _current.reset(token)


def trace_headers() -> dict[str, str]:
    context = current_trace_context()
    headers = {
        "X-Trace-ID": context.trace_id,
        "X-Request-ID": context.request_id,
        "X-Session-ID": context.session_id,
    }
    if context.turn_id is not None:
        headers["X-Turn-ID"] = str(context.turn_id)
    return {key: value for key, value in headers.items() if value != "-"}


def new_trace_id() -> str:
    return f"trace-{uuid4().hex}"


def new_request_id() -> str:
    return f"req-{uuid4().hex}"


def begin_turn_metrics() -> Token[TurnMetrics | None]:
    return _turn_metrics.set(TurnMetrics())


def reset_turn_metrics(token: Token[TurnMetrics | None]) -> None:
    _turn_metrics.reset(token)


def current_turn_metrics() -> TurnMetrics:
    return _turn_metrics.get() or TurnMetrics()


def record_turn_metrics(
    *,
    intent: str | None = None,
    handler: str | None = None,
    outcome: str | None = None,
    llm_calls: int = 0,
    llm_input_tokens: int | None = None,
    llm_output_tokens: int | None = None,
    pos_calls: int = 0,
    qdrant_calls: int = 0,
    nlu_duration_ms: int | None = None,
    entity_resolution_ms: int | None = None,
    handler_duration_ms: int | None = None,
    nlg_duration_ms: int | None = None,
) -> None:
    metrics = _turn_metrics.get()
    if metrics is None:
        return
    if intent is not None:
        metrics.intent = intent
    if handler is not None:
        metrics.handler = handler
    if outcome is not None:
        metrics.outcome = outcome
    metrics.llm_calls += llm_calls
    if llm_input_tokens is not None:
        metrics.llm_input_tokens += llm_input_tokens
    if llm_output_tokens is not None:
        metrics.llm_output_tokens += llm_output_tokens
    metrics.pos_calls += pos_calls
    metrics.qdrant_calls += qdrant_calls
    if nlu_duration_ms is not None:
        metrics.nlu_duration_ms += nlu_duration_ms
    if entity_resolution_ms is not None:
        metrics.entity_resolution_ms += entity_resolution_ms
    if handler_duration_ms is not None:
        metrics.handler_duration_ms += handler_duration_ms
    if nlg_duration_ms is not None:
        metrics.nlg_duration_ms += nlg_duration_ms


def store_completed_turn_metrics() -> None:
    metrics = _turn_metrics.get()
    _completed_turn_metrics.set(metrics.snapshot() if metrics is not None else None)


def consume_completed_turn_metrics() -> TurnMetrics | None:
    metrics = _completed_turn_metrics.get()
    _completed_turn_metrics.set(None)
    return metrics


def turn_metrics_payload(
    metrics: TurnMetrics,
    *,
    total_duration_ms: int,
) -> dict[str, object]:
    return {
        "intent": metrics.intent or "unresolved",
        "handler": metrics.handler or "none",
        "outcome": metrics.outcome or "unknown",
        "llm_calls": metrics.llm_calls,
        "pos_api_calls": metrics.pos_calls,
        "qdrant_calls": metrics.qdrant_calls,
        "tokens": {
            "input_tokens": metrics.llm_input_tokens,
            "output_tokens": metrics.llm_output_tokens,
            "total_tokens": metrics.llm_input_tokens + metrics.llm_output_tokens,
        },
        "timing": {
            "nlu_ms": metrics.nlu_duration_ms,
            "entity_resolution_ms": metrics.entity_resolution_ms,
            "handler_ms": metrics.handler_duration_ms,
            "nlg_ms": metrics.nlg_duration_ms,
            "total_duration_ms": total_duration_ms,
        },
    }


class TraceMiddleware:
    """
    Gắn trace headers cho toàn bộ vòng đời response ASGI, kể cả streaming.
    """

    def __init__(self, app: Any, *, service: str, pos_events: bool = False) -> None:
        self.app = app
        self.service = service
        self.pos_events = pos_events

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        incoming = {
            key.decode("latin-1").casefold(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        trace_id = _validated_or_default(incoming.get("x-trace-id"), new_trace_id())
        request_id = _validated_or_default(incoming.get("x-request-id"), new_request_id())
        session_id = _validated_or_default(incoming.get("x-session-id"), "-")
        turn_id = _parse_turn(incoming.get("x-turn-id"))
        token = bind_trace_context(
            trace_id=trace_id,
            request_id=request_id,
            session_id=session_id,
            turn_id=turn_id,
        )
        started = perf_counter()
        status_code = 500
        event_started = "pos_request_received" if self.pos_events else "request_started"
        event_completed = "pos_request_completed" if self.pos_events else "request_completed"
        _event(
            event_started,
            self.service,
            scope,
            method=scope.get("method"),
            _level=logging.DEBUG,
        )

        async def send_with_trace(message: dict[str, Any]) -> None:
            nonlocal status_code
            if message.get("type") == "http.response.start":
                status_code = int(message.get("status", 500))
                headers = list(message.get("headers", []))
                headers.extend(
                    [
                        (b"x-trace-id", trace_id.encode("ascii")),
                        (b"x-request-id", request_id.encode("ascii")),
                    ]
                )
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_trace)
            _event(
                event_completed,
                self.service,
                scope,
                status_code=status_code,
                duration_ms=round((perf_counter() - started) * 1000),
                _level=logging.DEBUG,
            )
        except Exception:
            _event(
                "pos_request_failed" if self.pos_events else "request_failed",
                self.service,
                scope,
                status_code=500,
                duration_ms=round((perf_counter() - started) * 1000),
                exc_info=True,
            )
            raise
        finally:
            reset_trace_context(token)


def _event(event: str, service: str, scope: dict[str, Any], **fields: object) -> None:

    exc_info = bool(fields.pop("exc_info", False))
    level = fields.pop("_level", None)
    trace_log(
        logging.getLogger("app.trace_middleware"),
        (
            logging.ERROR
            if exc_info
            else (level if isinstance(level, int) else logging.INFO)
        ),
        "TraceMiddleware",
        event,
        _exc_info=exc_info,
        service=service,
        path=scope.get("path", ""),
        **fields,
    )


def _validated_or_default(value: str | None, default: str) -> str:
    if value is None:
        return default
    normalized = value.strip()
    return normalized if _SAFE_ID.fullmatch(normalized) else default


def _parse_turn(value: str | None) -> int | None:
    if value is None or not value.isdigit():
        return None
    parsed = int(value)
    return parsed if parsed > 0 else None


# Cấu hình logging tập trung và che dữ liệu nhạy cảm cho toàn ứng dụng.

import hashlib
import json
import logging as std_logging
import re
import sys
from collections.abc import Mapping
from contextvars import ContextVar, Token
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

_CONSOLE_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
_VALID_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
_VALID_FORMATS = {"console", "json"}
_PHONE_PATTERN = re.compile(
    r"(?<![\d-])"
    r"(?![0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"
    r"(?!\d{4}-\d{2}-\d{2})\+?\d(?:[ -]?\d){8,14}(?!\d)"
)
_BEARER_PATTERN = re.compile(r"(?i)\bBearer\s+[^\s,;]+")
_UUID_PATTERN = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
_SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)\b(api[_-]?key|authorization|idempotency[_-]?key|password|secret|token)"
    r"\s*[:=]\s*[^\s,;]+"
)
_SENSITIVE_KEY_PARTS = {
    "api_key",
    "authorization",
    "booking_api_service_key",
    "content",
    "customer",
    "idempotency",
    "password",
    "payload",
    "phone",
    "qdrant_api_key",
    "request",
    "response",
    "secret",
    "token",
    "vector",
}
_RESERVED_RECORD_FIELDS = frozenset(std_logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {
    "message",
    "asctime",
}
_conversation_marker: ContextVar[str] = ContextVar("conversation_marker", default="-")
_correlation_marker: ContextVar[str] = ContextVar("correlation_marker", default="-")
_turn_marker: ContextVar[int | None] = ContextVar("turn_marker", default=None)
_service_name = "booking-chatbot"


class SafeConsoleFormatter(std_logging.Formatter):
    """
    Áp dụng các quy tắc che dữ liệu chung cho console log dễ đọc.
    """

    def format(self, record: std_logging.LogRecord) -> str:
        return _sanitize_text(super().format(record))


def mask_conversation_id(conversation_id: str) -> str:
    """
    Trả về marker ổn định nhưng không thể suy ngược ra conversation_id gốc.
    """
    return hashlib.sha256(conversation_id.encode("utf-8")).hexdigest()[:8]


def bind_conversation(conversation_id: str) -> Token[str]:
    """
    Bind marker conversation đã được che cho các log lồng nhau.
    """
    return _conversation_marker.set(mask_conversation_id(conversation_id))


def reset_conversation(token: Token[str]) -> None:
    """
    Khôi phục conversation logging context trước đó.
    """
    _conversation_marker.reset(token)


def bind_turn(turn_sequence: int) -> Token[int | None]:
    """
    Bind số turn dương trong conversation cho các trace log lồng nhau.
    """
    if type(turn_sequence) is not int or turn_sequence < 1:
        raise ValueError("Turn sequence must be a positive integer.")
    return _turn_marker.set(turn_sequence)


def reset_turn(token: Token[int | None]) -> None:
    """
    Khôi phục turn logging context trước đó.
    """
    _turn_marker.reset(token)


def bind_correlation_id(correlation_id: str | None) -> Token[str]:
    """
    Bind correlation marker an toàn do transport hiện tại cung cấp.
    """
    marker = mask_conversation_id(correlation_id) if correlation_id else "-"
    return _correlation_marker.set(marker)


def reset_correlation_id(token: Token[str]) -> None:
    """
    Khôi phục correlation logging context trước đó.
    """
    _correlation_marker.reset(token)


def trace_log(
    logger: std_logging.Logger,
    level: int,
    component: str,
    event: str,
    **fields: object,
) -> None:
    # Ghi một trace an toàn của component với structured fields.
    marker = _conversation_marker.get()
    correlation = _correlation_marker.get()
    turn = _turn_marker.get()
    exc_info = fields.pop("_exc_info", False) is True
    stacklevel = int(fields.pop("_stacklevel", 2))
    safe_fields = {key: _sanitize_value(key, value) for key, value in fields.items()}
    trace_context = current_trace_context()
    service = safe_fields.pop("service", _service_name)
    pathname, lineno, func_name, _stack_info = logger.findCaller(
        stack_info=False,
        stacklevel=stacklevel,
    )
    emitter_path = _project_relative_path(pathname)
    emitter = f"{emitter_path} :: {func_name}()"
    details = " ".join(f"{key}={value}" for key, value in safe_fields.items())
    component_marker = f"{component} #{turn}" if turn is not None else component
    message = f"[conv:{marker}] [{component_marker}] {event}"
    if trace_context.trace_id != "-":
        message = f"[trace:{trace_context.trace_id[:16]}] {message}"
    message = f"{message} emitter={emitter}"
    if details:
        message = f"{message} {details}"
    if correlation != "-":
        message = f"{message} correlation={correlation}"
    logger.log(
        level,
        message,
        extra={
            "service": service,
            "trace_id": trace_context.trace_id,
            "request_id": trace_context.request_id,
            "session_id": trace_context.session_id,
            "turn_id": trace_context.turn_id,
            "conversation": marker,
            "correlation": correlation,
            "component": component,
            "event": event,
            "turn_sequence": turn,
            "emitter": emitter,
            "emitter_path": emitter_path,
            "emitter_func": func_name,
            "emitter_lineno": lineno,
            **safe_fields,
        },
        exc_info=exc_info,
        stacklevel=stacklevel,
    )


def elapsed_ms(started_at: float) -> int:
    """
    Trả số mili giây đã trôi qua theo đồng hồ monotonic cho lifecycle log.
    """
    return max(0, round((perf_counter() - started_at) * 1000))


class JsonFormatter(std_logging.Formatter):
    """
    Format một LogRecord thành JSON đã che dữ liệu và giữ UTF-8.
    """

    def format(self, record: std_logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(
                record.created,
                tz=timezone.utc,
            ).isoformat(),
            "level": record.levelname,
            "service": getattr(record, "service", _service_name),
            "component": getattr(record, "component", record.name),
            "event": getattr(record, "event", "log_record"),
            "trace_id": getattr(
                record,
                "trace_id",
                current_trace_context().trace_id,
            ),
            "logger": record.name,
            "message": _sanitize_text(record.getMessage()),
        }
        for key, value in record.__dict__.items():
            if key in _RESERVED_RECORD_FIELDS or key.startswith("_"):
                continue
            payload[key] = _sanitize_value(key, value)
        if record.exc_info is not None:
            payload["exception"] = _sanitize_text(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(
    *,
    level: str = "INFO",
    log_format: str = "console",
    json_path: str | Path | None = None,
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 5,
    service: str = "booking-chatbot",
) -> None:
    # Thay toàn bộ logging handler của process bằng cấu hình tập trung.
    global _service_name
    normalized_level = _validate_level(level)
    normalized_format = _validate_format(log_format)
    if type(max_bytes) is not int or max_bytes <= 0:
        raise ValueError("Log rotation max bytes must be a positive integer.")
    if type(backup_count) is not int or backup_count < 0:
        raise ValueError("Log rotation backup count must be a non-negative integer.")
    if not isinstance(service, str) or not service.strip():
        raise ValueError("Logging service name must not be empty.")
    _service_name = service.strip()

    numeric_level = std_logging.getLevelNamesMapping()[normalized_level]
    console_formatter: std_logging.Formatter
    if normalized_format == "json":
        console_formatter = JsonFormatter()
    else:
        console_formatter = SafeConsoleFormatter(
            _CONSOLE_FORMAT,
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    console_handler = std_logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(console_formatter)

    handlers: list[std_logging.Handler] = [console_handler]
    normalized_path = _normalize_json_path(json_path)
    if normalized_path is not None:
        normalized_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            normalized_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setFormatter(JsonFormatter())
        handlers.append(file_handler)

    root_logger = std_logging.getLogger()
    _replace_handlers(root_logger, handlers)
    root_logger.setLevel(numeric_level)

    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
        logger = std_logging.getLogger(logger_name)
        _replace_handlers(logger, [])
        logger.setLevel(numeric_level)
        logger.propagate = True


def _replace_handlers(
    logger: std_logging.Logger,
    handlers: list[std_logging.Handler],
) -> None:
    for existing_handler in tuple(logger.handlers):
        logger.removeHandler(existing_handler)
        existing_handler.close()
    for handler in handlers:
        logger.addHandler(handler)


def _validate_level(level: str) -> str:
    if not isinstance(level, str) or level.strip().upper() not in _VALID_LEVELS:
        raise ValueError("Log level must be DEBUG, INFO, WARNING, ERROR, or CRITICAL.")
    return level.strip().upper()


def _validate_format(log_format: str) -> str:
    if not isinstance(log_format, str) or log_format.strip().casefold() not in _VALID_FORMATS:
        raise ValueError("Log format must be 'console' or 'json'.")
    return log_format.strip().casefold()


def _normalize_json_path(json_path: str | Path | None) -> Path | None:
    if json_path is None:
        return None
    if isinstance(json_path, str):
        if not json_path.strip():
            return None
        return Path(json_path.strip())
    if isinstance(json_path, Path):
        return json_path
    raise ValueError("JSON log path must be a filesystem path.")


def _project_relative_path(pathname: str) -> str:
    path = Path(pathname).resolve()
    try:
        return path.relative_to(Path(__file__).resolve().parents[2]).as_posix()
    except ValueError:
        return path.name


def _sanitize_value(key: str, value: object) -> object:
    normalized_key = key.casefold().replace("-", "_")
    if normalized_key in {
        "payload_keys",
        "request_keys",
        "response_keys",
        "content_length",
        "response_length",
        "message_length",
        "prompt_chars",
    }:
        return value
    if normalized_key in {
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "vector_candidate_count",
        "lexical_candidate_count",
    }:
        return value if type(value) is int and value >= 0 else "[REDACTED]"
    if any(part in normalized_key for part in _SENSITIVE_KEY_PARTS):
        return "[REDACTED]"
    if isinstance(value, str):
        return _sanitize_text(value)
    if isinstance(value, Mapping):
        return {
            str(nested_key): _sanitize_value(str(nested_key), nested_value)
            for nested_key, nested_value in value.items()
        }
    if isinstance(value, list | tuple):
        return [_sanitize_value(key, item) for item in value]
    if value is None or isinstance(value, bool | int | float):
        return value
    return str(value)


def _sanitize_text(value: str) -> str:
    protected: list[str] = []

    def protect_uuid(match: re.Match[str]) -> str:
        protected.append(match.group(0))
        return f"\x00UUID{len(protected) - 1}\x00"

    sanitized = _UUID_PATTERN.sub(protect_uuid, value)
    sanitized = _BEARER_PATTERN.sub("Bearer [REDACTED]", sanitized)
    sanitized = _SECRET_ASSIGNMENT_PATTERN.sub(
        lambda match: f"{match.group(1)}=[REDACTED]",
        sanitized,
    )
    sanitized = _PHONE_PATTERN.sub("[REDACTED_PHONE]", sanitized)
    for index, uuid_value in enumerate(protected):
        sanitized = sanitized.replace(f"\x00UUID{index}\x00", uuid_value)
    return sanitized


# Lưu `BookingContext` trong memory theo `conversation_id`.

from app.domain.booking_context import BookingContext


class ContextStore:
    """
    Lưu `BookingContext` ngay trong process hiện tại.
    Mọi thao tác đọc đều trả về bản sao để phần orchestration có thể mutate
    working copy mà không làm bẩn snapshot đang được lưu.
    """

    def __init__(self) -> None:
        self._contexts: dict[str, BookingContext] = {}

    async def get(self, conversation_id: str) -> BookingContext | None:
        """
        Trả về bản sao của context đã lưu mà không lộ snapshot gốc trong store.
        """
        context = self._contexts.get(conversation_id)
        return deepcopy(context) if context is not None else None

    async def save(self, context: BookingContext) -> None:
        """
        Lưu một snapshot tách biệt theo đúng conversation identifier của context.
        """
        self._contexts[context.conversation_id] = deepcopy(context)

    async def delete(self, conversation_id: str) -> None:
        """
        Xóa context của conversation nếu nó đang tồn tại trong store.
        """
        self._contexts.pop(conversation_id, None)

    async def get_copy(self, conversation_id: str) -> BookingContext:
        """
        Trả về working copy hoặc tạo context mới rồi snapshot vào store.
        """
        context = self._contexts.get(conversation_id)
        if context is None:
            context = BookingContext(conversation_id=conversation_id)
            self._contexts[conversation_id] = deepcopy(context)
        return deepcopy(context)

    def __len__(self) -> int:
        """
        Trả về số conversation context đang được giữ trong memory.
        """
        return len(self._contexts)
