"""Tests for runtime environment configuration loading."""

import os
from pathlib import Path

import pytest

from app.infrastructure.context_store import load_runtime_environment


def test_load_runtime_environment_reads_explicit_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "GEMINI_API_KEY=file-key\n"
        "GEMINI_MODEL=file-model\n"
        "GEMINI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    monkeypatch.delenv("GEMINI_BASE_URL", raising=False)

    loaded_path = load_runtime_environment(env_file)

    assert loaded_path == env_file.resolve()
    assert os.environ["GEMINI_API_KEY"] == "file-key"
    assert os.environ["GEMINI_MODEL"] == "file-model"
    assert os.environ["GEMINI_BASE_URL"].endswith("/v1beta/openai/")


def test_process_environment_overrides_env_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("GEMINI_API_KEY=file-key\n", encoding="utf-8")
    monkeypatch.setenv("GEMINI_API_KEY", "process-key")

    load_runtime_environment(env_file)

    assert os.environ["GEMINI_API_KEY"] == "process-key"
