"""Runtime configuration consumed by the application composition root."""

from dataclasses import dataclass, field
from pathlib import Path


def _default_booking_flow_path() -> Path:
    return Path(__file__).resolve().parents[1] / "dialog" / "flows" / "booking-flow.json"


@dataclass(frozen=True, slots=True)
class Settings:
    """Contains the runtime values required to assemble the booking application."""

    pos_base_url: str
    pos_timeout_seconds: float = 10.0
    booking_flow_path: Path = field(default_factory=_default_booking_flow_path)
    max_auto_transitions: int = 8
