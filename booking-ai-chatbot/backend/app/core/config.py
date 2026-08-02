"""Runtime configuration consumed by the application composition root."""

from dataclasses import dataclass, field
from pathlib import Path


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
    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "openrouter/free"
