"""Centralized, security-conscious application logging configuration."""

import json
import logging as std_logging
import re
import sys
from collections.abc import Mapping
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

_CONSOLE_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
_VALID_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
_VALID_FORMATS = {"console", "json"}
_PHONE_PATTERN = re.compile(r"(?<!\d)\+?\d(?:[ -]?\d){8,14}(?!\d)")
_BEARER_PATTERN = re.compile(r"(?i)\bBearer\s+[^\s,;]+")
_SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)\b(api[_-]?key|authorization|password|secret|token)\s*[:=]\s*[^\s,;]+"
)
_SENSITIVE_KEY_PARTS = {
    "api_key",
    "authorization",
    "booking_api_service_key",
    "content",
    "customer",
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
_RESERVED_RECORD_FIELDS = frozenset(
    std_logging.LogRecord("", 0, "", 0, "", (), None).__dict__
) | {"message", "asctime"}


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
            payload["exception"] = _sanitize_text(
                self.formatException(record.exc_info)
            )
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
        console_formatter = std_logging.Formatter(
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
        raise ValueError(
            "Log level must be DEBUG, INFO, WARNING, ERROR, or CRITICAL."
        )
    return level.strip().upper()


def _validate_format(log_format: str) -> str:
    if (
        not isinstance(log_format, str)
        or log_format.strip().casefold() not in _VALID_FORMATS
    ):
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
