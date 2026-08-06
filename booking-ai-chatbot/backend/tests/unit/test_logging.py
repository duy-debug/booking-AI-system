"""Tests for centralized application logging."""

import json
import logging
import os
import subprocess
import sys
from collections.abc import Iterator
from logging.handlers import RotatingFileHandler
from pathlib import Path
from types import TracebackType

import pytest

from app.infrastructure.context_store import (
    JsonFormatter,
    bind_conversation,
    bind_turn,
    configure_logging,
    mask_conversation_id,
    reset_conversation,
    reset_turn,
    trace_log,
)


@pytest.fixture(autouse=True)
def restore_logging_state() -> Iterator[None]:
    logger_names = ("", "uvicorn", "uvicorn.error", "uvicorn.access", "fastapi")
    states = {
        name: (
            list(logging.getLogger(name).handlers),
            logging.getLogger(name).level,
            logging.getLogger(name).propagate,
        )
        for name in logger_names
    }
    yield
    for name, (handlers, level, propagate) in states.items():
        logger = logging.getLogger(name)
        for handler in tuple(logger.handlers):
            logger.removeHandler(handler)
            if handler not in handlers:
                handler.close()
        for handler in handlers:
            logger.addHandler(handler)
        logger.setLevel(level)
        logger.propagate = propagate


def record(
    message: str,
    *,
    extra: dict[str, object] | None = None,
    exc_info: tuple[type[BaseException], BaseException, TracebackType | None] | None = None,
) -> logging.LogRecord:
    log_record = logging.LogRecord(
        name="app.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=exc_info,
    )
    for key, value in (extra or {}).items():
        setattr(log_record, key, value)
    return log_record


def test_configure_logging_creates_human_readable_console_handler() -> None:
    configure_logging(level="INFO", log_format="console")

    root = logging.getLogger()
    assert len(root.handlers) == 1
    assert isinstance(root.handlers[0], logging.StreamHandler)
    assert not isinstance(root.handlers[0], RotatingFileHandler)
    assert root.handlers[0].formatter is not None
    assert root.handlers[0].formatter._fmt == (
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )


def test_json_formatter_is_valid_one_line_unicode_with_extra_fields() -> None:
    rendered = JsonFormatter().format(
        record("Đặt lịch thành công", extra={"event": "booking_completed", "count": 2})
    )
    payload = json.loads(rendered)

    assert "\n" not in rendered
    assert "Đặt lịch thành công" in rendered
    assert payload["message"] == "Đặt lịch thành công"
    assert payload["event"] == "booking_completed"
    assert payload["count"] == 2
    assert set(("timestamp", "level", "logger", "message")) <= set(payload)


def test_json_formatter_serializes_and_redacts_exception() -> None:
    try:
        raise RuntimeError("failure for 0901234567")
    except RuntimeError as error:
        rendered = JsonFormatter().format(
            record("safe failure", exc_info=(RuntimeError, error, error.__traceback__))
        )
    payload = json.loads(rendered)

    assert "RuntimeError" in payload["exception"]
    assert "0901234567" not in rendered
    assert "[REDACTED_PHONE]" in rendered


def test_json_formatter_redacts_sensitive_message_and_nested_extra() -> None:
    rendered = JsonFormatter().format(
        record(
            "Authorization: Bearer private-token phone 0901234567",
            extra={
                "api_key": "top-secret",
                "metadata": {"phone": "0912345678", "safe": "visible"},
            },
        )
    )
    payload = json.loads(rendered)

    assert "private-token" not in rendered
    assert "top-secret" not in rendered
    assert "0901234567" not in rendered
    assert "0912345678" not in rendered
    assert payload["api_key"] == "[REDACTED]"
    assert payload["metadata"] == {"phone": "[REDACTED]", "safe": "visible"}


def test_conversation_marker_is_short_stable_and_non_reversible() -> None:
    conversation_id = "customer-conversation-123456789"

    marker = mask_conversation_id(conversation_id)

    assert len(marker) == 8
    assert marker == mask_conversation_id(conversation_id)
    assert marker not in conversation_id


def test_console_trace_redacts_phone_authorization_and_idempotency(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(level="INFO", log_format="console")
    token = bind_conversation("conversation-private-value")
    try:
        trace_log(
            logging.getLogger("app.trace"),
            logging.INFO,
            "Turn",
            "started",
            phone="0901234567",
            authorization="Bearer private-token",
            idempotency_key="full-idempotency-key",
        )
    finally:
        reset_conversation(token)
    output = capsys.readouterr().out

    assert "conversation-private-value" not in output
    assert "0901234567" not in output
    assert "private-token" not in output
    assert "full-idempotency-key" not in output
    assert "[conv:" in output
    assert "[Turn] started" in output


def test_console_trace_includes_bound_turn_sequence(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(level="INFO", log_format="console")
    conversation_token = bind_conversation("conversation-a")
    turn_token = bind_turn(3)
    try:
        trace_log(logging.getLogger("app.trace"), logging.INFO, "NLU", "resolved")
    finally:
        reset_turn(turn_token)
        reset_conversation(conversation_token)

    output = capsys.readouterr().out
    assert "[NLU #3] resolved" in output


def test_redaction_masks_phone_but_preserves_uuid(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(level="INFO", log_format="console")
    logging.getLogger("app.trace").info(
        "phone=0901234567 shop_id=11111111-1111-1111-1111-111111111111"
    )

    output = capsys.readouterr().out
    assert "0901234567" not in output
    assert "[REDACTED_PHONE]" in output
    assert "11111111-1111-1111-1111-111111111111" in output


def test_console_redaction_preserves_iso_timestamp(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(level="INFO", log_format="console")

    logging.getLogger("app.trace").info("timestamp-safe")
    output = capsys.readouterr().out

    assert "[REDACTED_PHONE]" not in output
    assert "timestamp-safe" in output


def test_optional_json_file_uses_rotation_utf8_and_creates_parent(
    tmp_path: Path,
) -> None:
    path = tmp_path / "nested" / "application.jsonl"
    configure_logging(
        log_format="console",
        json_path=path,
        max_bytes=1234,
        backup_count=2,
    )
    logging.getLogger("app.file").info("Xin chào")
    file_handler = next(
        handler
        for handler in logging.getLogger().handlers
        if isinstance(handler, RotatingFileHandler)
    )
    file_handler.flush()

    assert path.parent.is_dir()
    assert file_handler.maxBytes == 1234
    assert file_handler.backupCount == 2
    payload = json.loads(path.read_text(encoding="utf-8").strip())
    assert payload["message"] == "Xin chào"


def test_uvicorn_logs_propagate_once_without_own_handlers(
    capsys: pytest.CaptureFixture[str],
) -> None:
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(name).addHandler(logging.StreamHandler(sys.stdout))
        logging.getLogger(name).propagate = False

    configure_logging(log_format="console")
    logging.getLogger("uvicorn.access").info("single-access-record")
    output = capsys.readouterr().out

    assert output.count("single-access-record") == 1
    assert logging.getLogger("uvicorn.access").handlers == []
    assert logging.getLogger("uvicorn.access").propagate is True


def test_reconfiguration_replaces_instead_of_accumulating_handlers(tmp_path: Path) -> None:
    configure_logging(json_path=tmp_path / "first.jsonl")
    configure_logging(json_path=tmp_path / "second.jsonl")

    handlers = logging.getLogger().handlers
    assert len(handlers) == 2
    assert sum(isinstance(handler, RotatingFileHandler) for handler in handlers) == 1


@pytest.mark.parametrize(
    ("level", "log_format", "message"),
    [
        ("verbose", "console", "level"),
        ("INFO", "xml", "format"),
    ],
)
def test_invalid_level_or_format_is_rejected(
    level: str,
    log_format: str,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        configure_logging(level=level, log_format=log_format)


def test_importing_app_main_does_not_create_log_file(tmp_path: Path) -> None:
    backend_root = Path(__file__).resolve().parents[2]
    environment = os.environ.copy()
    environment.pop("LOG_JSON_PATH", None)
    environment["PYTHONPATH"] = str(backend_root)

    result = subprocess.run(
        [sys.executable, "-c", "import app.main"],
        cwd=tmp_path,
        env=environment,
        check=False,
    )

    assert result.returncode == 0
    assert list(tmp_path.iterdir()) == []
