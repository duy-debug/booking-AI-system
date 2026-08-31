"""Central structured logging for the POS backend."""

import json
import logging
import sys
from datetime import UTC, datetime

from app.utils.sensitive_data import sanitize_text, sanitize_value

_RESERVED = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {
    "message",
    "asctime",
}


# Formatter JSON dùng cho môi trường cần log có cấu trúc, kèm trace id để nối request qua nhiều layer.
class JsonFormatter(logging.Formatter):
    # Đưa LogRecord về JSON an toàn, đồng thời che dữ liệu nhạy cảm trước khi ghi log.
    def format(self, record: logging.LogRecord) -> str:
        from app.infrastructure.trace_context import current_trace_context

        context = current_trace_context()
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "service": "pos-backend",
            "component": getattr(record, "component", record.name),
            "event": getattr(record, "event", "log_record"),
            "trace_id": context.trace_id,
            "message": sanitize_text(record.getMessage()),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = sanitize_value(key, value)
        if record.exc_info:
            payload["exception"] = sanitize_text(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False, default=str)


# Formatter console phục vụ local/dev, vẫn gắn trace/session/turn để debug cùng một request dễ hơn.
class ConsoleFormatter(logging.Formatter):
    # Format log dạng người đọc được và sanitize message để tránh lộ dữ liệu nhạy cảm.
    def format(self, record: logging.LogRecord) -> str:
        from app.infrastructure.trace_context import current_trace_context

        context = current_trace_context()
        base = super().format(record)
        parts = [f"[trace={context.trace_id}]"]
        if context.session_id != "-":
            parts.append(f"[session={context.session_id}]")
        if context.turn_id is not None:
            parts.append(f"[turn={context.turn_id}]")
        return sanitize_text(
            f"{base} {' '.join(parts)}"
        )


# Cấu hình logging tập trung cho POS backend để mọi module dùng cùng format và level.
def configure_logging(*, level: str = "INFO", log_format: str = "console") -> None:
    normalized_level = level.strip().upper()
    if normalized_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ValueError("Invalid POS log level.")
    normalized_format = log_format.strip().casefold()
    if normalized_format not in {"console", "json"}:
        raise ValueError("Invalid POS log format.")
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        JsonFormatter()
        if normalized_format == "json"
        else ConsoleFormatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    )
    root = logging.getLogger()
    # Xóa handler cũ để gọi configure nhiều lần trong test/startup không bị duplicate log.
    for existing in tuple(root.handlers):
        root.removeHandler(existing)
        existing.close()
    root.addHandler(handler)
    root.setLevel(logging.getLevelNamesMapping()[normalized_level])
    for name in ("uvicorn", "uvicorn.error", "fastapi"):
        child = logging.getLogger(name)
        child.handlers.clear()
        child.setLevel(logging.getLevelNamesMapping()[normalized_level])
        child.propagate = True
    access_logger = logging.getLogger("uvicorn.access")
    access_logger.handlers.clear()
    access_logger.setLevel(logging.WARNING)
    access_logger.propagate = False


# Helper ghi log nghiệp vụ có cấu trúc, tự gắn trace context và sanitize các field động.
def log_event(
    level: int,
    component: str,
    event: str,
    *,
    exc_info: bool = False,
    message: str | None = None,
    **fields: object,
) -> None:
    from app.infrastructure.trace_context import current_trace_context

    context = current_trace_context()
    safe = {key: sanitize_value(key, value) for key, value in fields.items()}
    logging.getLogger(f"app.{component}").log(
        level,
        message or event,
        extra={
            "component": component,
            "event": event,
            "trace_id": context.trace_id,
            "request_id": context.request_id,
            "session_id": context.session_id,
            "turn_id": context.turn_id,
            **safe,
        },
        exc_info=exc_info,
    )
