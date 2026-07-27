from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from app.application.intent_router import RouteTarget, route_intent
from app.application.nlu import StructuredNLU
from app.application.orchestrator import ConversationOrchestrator
from app.core.exceptions import AppError
from app.domain.intent import Intent
from app.domain.nlu import NLUResult


@pytest.mark.asyncio
async def test_nlu_returns_structured_entities_without_calling_tool():
    result = await StructuredNLU().parse("Tôi muốn đặt lịch 2026-07-25 lúc 14:30, số 0901234567")

    assert result.intent is Intent.CREATE_BOOKING
    assert result.resource == "booking"
    assert result.operation == "create"
    assert result.entities["booking_date"] == "2026-07-25"
    assert result.entities["start_time"] == "14:30"
    assert result.entities["phone"] == "0901234567"


# Trích xuất UUID booking để lượt tiếp theo của lookup workflow không phụ thuộc label UI.
@pytest.mark.asyncio
async def test_nlu_extracts_booking_id() -> None:
    booking_id = "6f1f99b2-b3f7-4d13-a95e-98e1c808a805"

    result = await StructuredNLU().parse(
        f"Tra cứu booking {booking_id}, số 0901234567"
    )

    assert result.intent is Intent.LOOKUP_BOOKING
    assert result.entities["booking_id"] == booking_id
    assert result.entities["phone"] == "0901234567"


@pytest.mark.asyncio
async def test_nlu_understands_relative_date_and_short_hour() -> None:
    with patch("app.application.nlu.business_today", return_value=date(2026, 7, 27)):
        result = await StructuredNLU().parse(
            "tôi muốn đặt booking ngày mai lúc 7h"
        )

    assert result.intent is Intent.CREATE_BOOKING
    assert result.resource == "booking"
    assert result.operation == "create"
    assert result.entities["booking_date"] == "2026-07-28"
    assert result.entities["start_time"] == "07:00"


def test_router_sends_dynamic_information_to_information_handler():
    result = NLUResult(
        intent=Intent.SHOP_INFO,
        resource="shop",
        operation="list",
    )

    assert route_intent(result) is RouteTarget.INFORMATION


@pytest.mark.asyncio
async def test_guard_blocks_admin_operation_before_handler():
    handler = AsyncMock()
    orchestrator = ConversationOrchestrator(
        nlu=StructuredNLU(),
        handlers={RouteTarget.CLARIFY: handler},
        conversation_store=AsyncMock(),
    )

    with pytest.raises(AppError) as exc:
        await orchestrator.handle("xóa nhân viên", "conversation-1")

    assert exc.value.code == "ADMIN_OPERATION_NOT_ALLOWED"
    handler.handle.assert_not_awaited()
