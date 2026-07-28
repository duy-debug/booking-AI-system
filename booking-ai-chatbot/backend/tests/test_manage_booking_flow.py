from datetime import date, timedelta
from unittest.mock import AsyncMock

import pytest

from app.application.booking_workflow import BookingWorkflow
from app.application.manage_booking_flow import ManageBookingFlow
from app.core.exceptions import AppError
from app.domain.intent import Intent
from app.domain.models import PendingAction
from app.domain.nlu import NLUResult
from app.domain.state import ConversationState
from app.tools.mutation import MutationTools

BOOKING_ID = "6f1f99b2-b3f7-4d13-a95e-98e1c808a805"


class MemoryStore:
    def __init__(self) -> None:
        self.states: dict[str, ConversationState] = {}
        self.pending: dict[str, PendingAction] = {}

    async def save_state(self, state: ConversationState) -> None:
        self.states[state.conversation_id] = state

    async def get_state(self, conversation_id: str) -> ConversationState:
        return self.states.get(
            conversation_id, ConversationState(conversation_id=conversation_id)
        )

    async def delete_state(self, conversation_id: str) -> None:
        self.states.pop(conversation_id, None)

    async def save_pending(self, action: PendingAction) -> None:
        self.pending[action.conversation_id] = action

    async def get_pending(self, conversation_id: str) -> PendingAction | None:
        return self.pending.get(conversation_id)

    async def delete_pending(self, conversation_id: str) -> None:
        self.pending.pop(conversation_id, None)


def nlu(intent: Intent) -> NLUResult:
    return NLUResult(intent=intent, resource="booking", operation=intent.value, entities={})


def build(action: str):
    store = MemoryStore()
    gateway = AsyncMock()
    gateway.lookup_booking.return_value = {
        "booking_id": BOOKING_ID,
        "status": "confirmed",
        "booking_date": "2026-08-01",
        "start_time": "10:00",
    }
    gateway.update_booking.return_value = {"booking_id": BOOKING_ID, "status": "confirmed"}
    gateway.is_reschedule_available.return_value = True
    mutations = MutationTools(BookingWorkflow(gateway, store))
    return store, gateway, ManageBookingFlow(action, store, gateway, mutations)


@pytest.mark.asyncio
async def test_cancel_requires_owner_lookup_and_confirmation() -> None:
    store, gateway, flow = build("cancel_booking")
    result = await flow.handle(
        "c1",
        nlu(Intent.CANCEL_BOOKING),
        {
            "entity": "booking_manage",
            "value": {
                "booking_id": BOOKING_ID,
                "phone": "0901234567",
                "cancel_reason": "Đổi kế hoạch",
            },
        },
    )
    assert result["ui"]["type"] == "booking_cancel_summary"
    gateway.update_booking.assert_not_called()
    token = result["ui"]["data"]["confirmation_token"]
    confirmed = await flow.handle(
        "c1",
        nlu(Intent.CANCEL_BOOKING),
        {"entity": "confirmation_token", "value": token},
    )
    assert confirmed["ui"]["type"] == "booking_result"
    assert confirmed["ui"]["data"]["operation"] == "cancel_booking"
    gateway.update_booking.assert_awaited_once_with(
        BOOKING_ID,
        {"status": "cancelled", "cancel_reason": "Đổi kế hoạch"},
    )
    assert "c1" not in store.pending


@pytest.mark.asyncio
async def test_update_requires_change_then_confirms_exact_payload() -> None:
    _, gateway, flow = build("update_booking")
    new_date = (date.today() + timedelta(days=2)).isoformat()
    result = await flow.handle(
        "c2",
        nlu(Intent.UPDATE_BOOKING),
        {
            "entity": "booking_manage",
            "value": {
                "booking_id": BOOKING_ID,
                "phone": "0901234567",
                "booking_date": new_date,
                "start_time": "14:30",
            },
        },
    )
    assert result["ui"]["type"] == "booking_update_summary"
    gateway.update_booking.assert_not_called()
    token = result["ui"]["data"]["confirmation_token"]
    confirmed = await flow.handle(
        "c2",
        nlu(Intent.UPDATE_BOOKING),
        {"entity": "confirmation_token", "value": token},
    )
    gateway.update_booking.assert_awaited_once_with(
        BOOKING_ID, {"booking_date": new_date, "start_time": "14:30"}
    )
    assert confirmed["ui"]["data"]["operation"] == "update_booking"


@pytest.mark.asyncio
async def test_cancel_rejects_already_cancelled_booking() -> None:
    _, gateway, flow = build("cancel_booking")
    gateway.lookup_booking.return_value["status"] = "cancelled"
    with pytest.raises(AppError) as exc:
        await flow.handle(
            "c3",
            nlu(Intent.CANCEL_BOOKING),
            {
                "entity": "booking_manage",
                "value": {"booking_id": BOOKING_ID, "phone": "0901234567"},
            },
        )
    assert exc.value.code == "BOOKING_ALREADY_CANCELLED"


@pytest.mark.asyncio
async def test_update_rejects_unavailable_slot_before_confirmation() -> None:
    store, gateway, flow = build("update_booking")
    gateway.is_reschedule_available.return_value = False
    with pytest.raises(AppError) as exc:
        await flow.handle(
            "c4",
            nlu(Intent.UPDATE_BOOKING),
            {
                "entity": "booking_manage",
                "value": {
                    "booking_id": BOOKING_ID,
                    "phone": "0901234567",
                    "booking_date": (date.today() + timedelta(days=2)).isoformat(),
                    "start_time": "14:30",
                },
            },
        )
    assert exc.value.code == "RESCHEDULE_SLOT_UNAVAILABLE"
    assert "c4" not in store.pending
