"""Create the FastAPI application and own its dependency lifespan."""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import Settings, load_runtime_environment
from app.core.logging import configure_logging
from app.dependencies import application_container_lifespan
from app.transport.chat_api import router as chat_router


def _environment_bool(name: str, *, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    normalized = raw_value.strip().casefold()
    if normalized in {"true", "1", "yes", "on"}:
        return True
    if normalized in {"false", "0", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean value.")


def _enabled_qdrant_port(enabled: bool) -> int:
    if not enabled:
        return 6333
    raw_port = os.getenv("QDRANT_PORT", "6333")
    try:
        return int(raw_port)
    except ValueError as error:
        raise ValueError("QDRANT_PORT must be an integer.") from error


def create_app(settings: Settings) -> FastAPI:
    """Create one application whose container lives for the app lifespan."""

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        async with application_container_lifespan(settings) as container:
            application.state.application_container = container
            yield

    application = FastAPI(lifespan=lifespan)
    application.include_router(chat_router)
    return application


load_runtime_environment()

_knowledge_qdrant_enabled = _environment_bool("KNOWLEDGE_QDRANT_ENABLED")
_log_level = os.getenv("LOG_LEVEL", "INFO")
_log_format = os.getenv("LOG_FORMAT", "console")
_log_json_path = os.getenv("LOG_JSON_PATH") or None
_log_max_bytes = int(os.getenv("LOG_MAX_BYTES", str(10 * 1024 * 1024)))
_log_backup_count = int(os.getenv("LOG_BACKUP_COUNT", "5"))
_log_full_instructions = _environment_bool("LOG_FULL_INSTRUCTIONS")
_log_raw_chat_messages = _environment_bool("LOG_RAW_CHAT_MESSAGES")
_log_raw_chat_responses = _environment_bool("LOG_RAW_CHAT_RESPONSES")

configure_logging(
    level=_log_level,
    log_format=_log_format,
    json_path=_log_json_path,
    max_bytes=_log_max_bytes,
    backup_count=_log_backup_count,
)

app = create_app(
    Settings(
        pos_base_url=os.getenv("BOOKING_API_URL", "http://localhost:8000"),
        llm_provider=os.getenv("LLM_PROVIDER", "gemini"),
        gemini_api_key=os.getenv("GEMINI_API_KEY") or None,
        gemini_base_url=os.getenv(
            "GEMINI_BASE_URL",
            "https://generativelanguage.googleapis.com/v1beta/openai/",
        ),
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        llm_max_retries=int(os.getenv("LLM_MAX_RETRIES", "0")),
        dialog_intent_tool_enabled=_environment_bool(
            "DIALOG_INTENT_TOOL_ENABLED", default=True
        ),
        embedding_model_name=os.getenv(
            "EMBED_MODEL_NAME",
            "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        ),
        qdrant_host=os.getenv("QDRANT_HOST", "localhost"),
        qdrant_port=_enabled_qdrant_port(_knowledge_qdrant_enabled),
        qdrant_api_key=os.getenv("QDRANT_API_KEY") or None,
        qdrant_collection=os.getenv("QDRANT_COLLECTION", "kb_chunks"),
        knowledge_qdrant_enabled=_knowledge_qdrant_enabled,
        rag_hybrid_score_threshold=float(
            os.getenv("RAG_HYBRID_SCORE_THRESHOLD", "0.45")
        ),
        log_level=_log_level,
        log_format=_log_format,
        log_json_path=_log_json_path,
        log_max_bytes=_log_max_bytes,
        log_backup_count=_log_backup_count,
        log_full_instructions=_log_full_instructions,
        log_raw_chat_messages=_log_raw_chat_messages,
        log_raw_chat_responses=_log_raw_chat_responses,
    )
)
