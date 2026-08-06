"""Contract-faithful structured NLU provider used by transport integration tests."""

import json
import re
from datetime import date, timedelta

from app.infrastructure.gemini_client import LLMMessage, LLMResponse

_STATE_PATTERN = re.compile(r"Current state: ([a-z_]+)\.")
_DATE_PATTERN = re.compile(r"Current business date: (\d{4}-\d{2}-\d{2})\.")
_CLOCK_PATTERN = re.compile(r"(?<!\d)(\d{1,2}):(\d{2})(?!\d)")
_SLASH_DATE_PATTERN = re.compile(r"(?<!\d)(\d{1,2})/(\d{1,2})/(\d{4})(?!\d)")
_NUMBER_PATTERN = re.compile(r"(?<!\d)(\d{1,3})(?!\d)")


class StructuredNLUGateway:
    """Return Gemini-shaped JSON while keeping endpoint tests network-free."""

    def __init__(self) -> None:
        self.calls = 0

    async def generate(
        self,
        messages: list[LLMMessage],
        *,
        tools: list[dict[str, object]] | None = None,
    ) -> LLMResponse:
        self.calls += 1
        system = messages[0].content
        user = messages[-1].content.strip()
        state_match = _STATE_PATTERN.search(system)
        state = state_match.group(1) if state_match else "idle"
        intent, entities, entity_kind, entity_query = _classify(user, state, system)
        return LLMResponse(
            content=json.dumps(
                {
                    "intent": intent,
                    "confidence": 0.99,
                    "entities": entities,
                    "entity_kind": entity_kind,
                    "entity_query": entity_query,
                }
            )
        )


def _classify(
    user: str,
    state: str,
    system: str,
) -> tuple[str, dict[str, object], str | None, str | None]:
    folded = user.casefold()
    if state == "idle":
        if "xem" in folded and "?" not in folded:
            return "list_shops", {}, None, None
        if "?" in user or "massage" in folded:
            return "ask_question", {"query": user}, None, None
        if any(token in folded for token in ("unknown", "payload", "private", "hello")):
            return "unknown", {}, None, None
        entities: dict[str, object] = {}
        clock = _CLOCK_PATTERN.search(user)
        current_date = _DATE_PATTERN.search(system)
        if clock is not None:
            entities["start_time"] = f"{int(clock.group(1)):02d}:{clock.group(2)}"
        if current_date is not None and "ng" in folded and "mai" in folded:
            entities["booking_date"] = (
                date.fromisoformat(current_date.group(1)) + timedelta(days=1)
            ).isoformat()
        return "start_booking", entities, None, None
    if state == "selecting_shop":
        if user in {"Shibuya", "Tokyo"}:
            return "select_store", {}, "shop", user
        return "unknown", {}, None, None
    if state == "selecting_date":
        match = _SLASH_DATE_PATTERN.search(user)
        if match is None:
            return "unknown", {}, None, None
        value = date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
        return "select_date", {"booking_date": value.isoformat()}, None, None
    if state == "selecting_people":
        match = _NUMBER_PATTERN.search(user)
        return (
            ("select_people", {"number_of_people": int(match.group(1))}, None, None)
            if match is not None
            else ("unknown", {}, None, None)
        )
    if state == "selecting_duration":
        if "xem" in folded:
            return "list_services", {}, None, None
        match = _NUMBER_PATTERN.search(user)
        return (
            ("select_duration", {"duration_minutes": int(match.group(1))}, None, None)
            if match is not None
            else ("unknown", {}, None, None)
        )
    if state == "selecting_service":
        if user == "Aromatherapy":
            return "select_course", {}, "course", user
        if "add-on" in folded and folded.startswith("kh"):
            return "deny", {}, None, None
        return "list_services", {}, None, None
    if state in {"selecting_time", "booking_failed"}:
        match = _CLOCK_PATTERN.search(user)
        return (
            (
                "select_time",
                {"start_time": f"{int(match.group(1)):02d}:{match.group(2)}"},
                None,
                None,
            )
            if match is not None
            else ("unknown", {}, None, None)
        )
    if state == "verifying_phone":
        return "deny", {}, None, None
    if state == "awaiting_confirmation":
        if "ng" in folded:
            return "change_info", {"change_target": "date"}, None, None
        return "confirm", {}, None, None
    if state in {"completed", "cancelled"} and folded.startswith("đổi "):
        return "change_info", {"change_target": "date"}, None, None
    return "unknown", {}, None, None
