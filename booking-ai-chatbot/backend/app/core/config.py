"""Runtime configuration consumed by the application composition root."""

from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


def _default_env_path() -> Path:
    return Path(__file__).resolve().parents[2] / ".env"


def load_runtime_environment(env_file: Path | None = None) -> Path:
    """Load backend-local defaults without overriding the process environment."""
    resolved_path = (env_file or _default_env_path()).resolve()
    load_dotenv(dotenv_path=resolved_path, override=False)
    return resolved_path


def _default_booking_flow_path() -> Path:
    return Path(__file__).resolve().parents[1] / "dialog" / "flows" / "booking-flow.json"


def _default_change_handlers_path() -> Path:
    return Path(__file__).resolve().parents[1] / "dialog" / "flows" / "change-handlers.json"


@dataclass(frozen=True, slots=True)
class Settings:
    """Contains the runtime values required to assemble the booking application."""

    pos_base_url: str
    pos_timeout_seconds: float = 10.0
    booking_flow_path: Path = field(default_factory=_default_booking_flow_path)
    change_handlers_path: Path = field(default_factory=_default_change_handlers_path)
    max_auto_transitions: int = 8
    enable_llm_nlu_fallback: bool = True
    llm_nlu_min_confidence: float = 0.70
    llm_provider: str = "gemini"
    gemini_api_key: str | None = None
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    gemini_model: str = "gemini-2.5-flash"
    llm_max_retries: int = 0
    dialog_intent_tool_enabled: bool = True
    embedding_model_name: str = (
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    )
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_api_key: str | None = None
    qdrant_collection: str = "kb_chunks"
    knowledge_qdrant_enabled: bool = False
    rag_hybrid_score_threshold: float = 0.45
    log_level: str = "INFO"
    log_format: str = "console"
    log_json_path: str | None = None
    log_max_bytes: int = 10 * 1024 * 1024
    log_backup_count: int = 5
    log_full_instructions: bool = False
    log_raw_chat_messages: bool = False
