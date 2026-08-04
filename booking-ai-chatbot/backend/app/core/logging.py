"""Centralized, security-conscious application logging configuration."""

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
from time import perf_counter

_CONSOLE_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
_VALID_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
_VALID_FORMATS = {"console", "json"}
_PHONE_PATTERN = re.compile(
    r"(?<![\d-])"
    r"(?![0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"
    r"(?!\d{4}-\d{2}-\d{2})\+?\d(?:[ -]?\d){8,14}(?!\d)"
)
_BEARER_PATTERN = re.compile(r"(?i)\bBearer\s+[^\s,;]+")
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


class SafeConsoleFormatter(std_logging.Formatter):
    """Apply the shared redaction rules to human-readable console output."""

    def format(self, record: std_logging.LogRecord) -> str:
        return _sanitize_text(super().format(record))


def mask_conversation_id(conversation_id: str) -> str:
    """Return a stable non-reversible marker without exposing the identifier."""
    return hashlib.sha256(conversation_id.encode("utf-8")).hexdigest()[:8]


def bind_conversation(conversation_id: str) -> Token[str]:
    """Bind one masked conversation marker for nested adapter logs."""
    return _conversation_marker.set(mask_conversation_id(conversation_id))


def reset_conversation(token: Token[str]) -> None:
    """Restore the prior conversation logging context."""
    _conversation_marker.reset(token)


def bind_turn(turn_sequence: int) -> Token[int | None]:
    """Bind a positive conversation-local turn number for nested trace logs."""
    if type(turn_sequence) is not int or turn_sequence < 1:
        raise ValueError("Turn sequence must be a positive integer.")
    return _turn_marker.set(turn_sequence)


def reset_turn(token: Token[int | None]) -> None:
    """Restore the prior turn logging context."""
    _turn_marker.reset(token)


def bind_correlation_id(correlation_id: str | None) -> Token[str]:
    """Bind a safe correlation marker supplied by the current transport."""
    marker = mask_conversation_id(correlation_id) if correlation_id else "-"
    return _correlation_marker.set(marker)


def reset_correlation_id(token: Token[str]) -> None:
    """Restore the prior correlation logging context."""
    _correlation_marker.reset(token)


def trace_log(
    logger: std_logging.Logger,
    level: int,
    component: str,
    event: str,
    **fields: object,
) -> None:
    """Write one safe component trace with structured fields."""
    marker = _conversation_marker.get()
    correlation = _correlation_marker.get()
    turn = _turn_marker.get()
    safe_fields = {key: _sanitize_value(key, value) for key, value in fields.items()}
    details = " ".join(f"{key}={value}" for key, value in safe_fields.items())
    component_marker = f"{component} #{turn}" if turn is not None else component
    message = f"[conv:{marker}] [{component_marker}] {event}"
    if details:
        message = f"{message} {details}"
    if correlation != "-":
        message = f"{message} correlation={correlation}"
    logger.log(
        level,
        message,
        extra={
            "conversation": marker,
            "correlation": correlation,
            "component": component,
            "event": event,
            "turn_sequence": turn,
            **safe_fields,
        },
    )


def elapsed_ms(started_at: float) -> int:
    """Return monotonic elapsed milliseconds for external/lifecycle logs."""
    return max(0, round((perf_counter() - started_at) * 1000))


class JsonFormatter(std_logging.Formatter):
    """Format one LogRecord as one redacted UTF-8-friendly JSON object."""

    def format(self, record: std_logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(
                record.created,
                tz=timezone.utc,
            ).isoformat(),
            "level": record.levelname,
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
) -> None:
    """Replace process logging handlers with one centralized configuration."""
    normalized_level = _validate_level(level)
    normalized_format = _validate_format(log_format)
    if type(max_bytes) is not int or max_bytes <= 0:
        raise ValueError("Log rotation max bytes must be a positive integer.")
    if type(backup_count) is not int or backup_count < 0:
        raise ValueError("Log rotation backup count must be a non-negative integer.")

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


def _sanitize_value(key: str, value: object) -> object:
    normalized_key = key.casefold().replace("-", "_")
    if normalized_key in {
        "input_tokens",
        "output_tokens",
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
    sanitized = _BEARER_PATTERN.sub("Bearer [REDACTED]", value)
    sanitized = _SECRET_ASSIGNMENT_PATTERN.sub(
        lambda match: f"{match.group(1)}=[REDACTED]",
        sanitized,
    )
    return _PHONE_PATTERN.sub("[REDACTED_PHONE]", sanitized)
