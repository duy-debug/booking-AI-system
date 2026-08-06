"""Central structured logging for the POS backend."""

import json
import logging
import sys
from datetime import UTC, datetime, timezone

from app.utils.sensitive_data import sanitize_text, sanitize_value

_RESERVED = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {
    "message",
    "asctime",
}


class JsonFormatter(logging.Formatter):
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


class ConsoleFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        from app.infrastructure.trace_context import current_trace_context

        context = current_trace_context()
        base = super().format(record)
        return sanitize_text(
            f"{base} [trace={context.trace_id}] [session={context.session_id}] "
            f"[turn={context.turn_id or '-'}]"
        )


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
    for existing in tuple(root.handlers):
        root.removeHandler(existing)
        existing.close()
    root.addHandler(handler)
    root.setLevel(logging.getLevelNamesMapping()[normalized_level])
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
        child = logging.getLogger(name)
        child.handlers.clear()
        child.propagate = True


def log_event(
    level: int,
    component: str,
    event: str,
    *,
    exc_info: bool = False,
    **fields: object,
) -> None:
    from app.infrastructure.trace_context import current_trace_context

    context = current_trace_context()
    safe = {key: sanitize_value(key, value) for key, value in fields.items()}
    logging.getLogger(f"app.{component}").log(
        level,
        event,
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
