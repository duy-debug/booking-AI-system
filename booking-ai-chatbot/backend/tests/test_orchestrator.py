from unittest.mock import AsyncMock

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
