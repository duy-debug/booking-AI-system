from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from app.application.create_booking_flow import CreateBookingFlow
from app.core.exceptions import AppError
from app.domain.intent import Intent
from app.domain.models import PendingAction
from app.domain.nlu import NLUResult
from app.domain.state import ConversationState, ConversationStep


class MemoryConversationStore:
    def __init__(self) -> None:
        self.states: dict[str, ConversationState] = {}
        self.pending: dict[str, PendingAction] = {}

    # Lưu state độc lập theo conversation để mô phỏng Redis trong unit test.
    async def save_state(self, state: ConversationState) -> None:
        self.states[state.conversation_id] = state

    # Trả state đang có hoặc tạo state mới cho conversation.
    async def get_state(self, conversation_id: str) -> ConversationState:
        return self.states.get(
            conversation_id,
            ConversationState(conversation_id=conversation_id),
        )

    # Xóa state khi test cần mô phỏng kết thúc phiên.
    async def delete_state(self, conversation_id: str) -> None:
        self.states.pop(conversation_id, None)

    # Lưu pending action để flow có thể tái sử dụng cùng confirmation token.
    async def save_pending(self, action: PendingAction) -> None:
        self.pending[action.conversation_id] = action

    # Trả pending action hiện tại.
    async def get_pending(self, conversation_id: str) -> PendingAction | None:
        return self.pending.get(conversation_id)

    # Xóa pending action sau mutation thành công.
    async def delete_pending(self, conversation_id: str) -> None:
        self.pending.pop(conversation_id, None)


# Tạo NLU result cho intent create mà không phụ thuộc bộ phân loại từ khóa.
def create_nlu(**entities) -> NLUResult:
    return NLUResult(
        intent=Intent.CREATE_BOOKING,
        resource="booking",
        operation="create",
        entities=entities,
    )


@pytest.mark.asyncio
async def test_first_step_returns_verified_shop_options():
    store = MemoryConversationStore()
    mutation = AsyncMock()
    flow = CreateBookingFlow(store, mutation)

    with patch(
        "app.application.create_booking_flow.read_only.list_shops",
        new=AsyncMock(
            return_value=[
                {
                    "shop_id": "shop-1",
                    "name": "東京中央店",
                    "address": "東京都中央区",
                }
            ]
        ),
    ):
        result = await flow.handle("conversation-1", create_nlu())

    assert result["ui"]["type"] == "shop_options"
    assert result["ui"]["options"][0]["id"] == "shop-1"
    assert store.states["conversation-1"].step is ConversationStep.COLLECT_SHOP


@pytest.mark.asyncio
async def test_invalid_course_from_another_shop_is_rejected():
    store = MemoryConversationStore()
    store.states["conversation-1"] = ConversationState(
        conversation_id="conversation-1",
        intent=Intent.CREATE_BOOKING.value,
        entities={"shop_id": "shop-1"},
    )
    flow = CreateBookingFlow(store, AsyncMock())

    with patch(
        "app.application.create_booking_flow.read_only.list_courses",
        new=AsyncMock(return_value=[]),
    ):
        with pytest.raises(AppError) as exc:
            await flow.handle(
                "conversation-1",
                create_nlu(),
                selection={"entity": "main_course_id", "value": "course-other"},
            )

    assert exc.value.code == "INVALID_MAIN_COURSE"


@pytest.mark.asyncio
async def test_group_booking_rejects_specific_therapist_request():
    store = MemoryConversationStore()
    store.states["conversation-1"] = ConversationState(
        conversation_id="conversation-1",
        intent=Intent.CREATE_BOOKING.value,
        entities={"number_of_people": 2},
    )
    flow = CreateBookingFlow(store, AsyncMock())

    with pytest.raises(AppError) as exc:
        await flow.handle(
            "conversation-1",
            create_nlu(),
            selection={"entity": "therapist_request_type", "value": "specific"},
        )

    assert exc.value.code == "GROUP_BOOKING_THERAPIST_MUST_BE_AUTO"


@pytest.mark.asyncio
async def test_single_booking_asks_for_therapist_preference_before_customer():
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    store = MemoryConversationStore()
    store.states["conversation-1"] = ConversationState(
        conversation_id="conversation-1",
        intent=Intent.CREATE_BOOKING.value,
        entities={
            "shop_id": "shop-1",
            "main_course_id": "course-1",
            "addon_course_ids": [],
            "number_of_people": 1,
            "booking_date": tomorrow,
            "start_time": "10:00",
        },
    )
    flow = CreateBookingFlow(store, AsyncMock())

    result = await flow.handle("conversation-1", create_nlu())

    assert result["ui"]["type"] == "therapist_request_options"
    assert result["missing_entities"][0] == "therapist_request_type"


@pytest.mark.asyncio
async def test_complete_create_booking_flow_uses_confirmation_gate():
    store = MemoryConversationStore()
    mutation = AsyncMock()

    # Lưu pending giống MutationTools thật để flow có thể đọc lại confirmation.
    async def prepare(conversation_id, action, payload):
        pending = PendingAction(
            conversation_id=conversation_id,
            action=action,
            payload=payload,
            confirmation_token="ABC123DEF456",
        )
        await store.save_pending(pending)
        return pending

    mutation.prepare.side_effect = prepare
    mutation.confirm.return_value = {
        "booking_id": "booking-1",
        "status": "confirmed",
    }
    flow = CreateBookingFlow(store, mutation)
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    available_slots = {
        "data": [
            {
                "start_time": "10:00:00",
                "end_time": "11:00:00",
                "duration_minutes": 60,
                "available": True,
            }
        ],
        "meta": {},
    }

    with (
        patch(
            "app.application.create_booking_flow.read_only.list_shops",
            new=AsyncMock(
                return_value=[
                    {
                        "shop_id": "shop-1",
                        "name": "東京中央店",
                        "address": "東京都中央区",
                    }
                ]
            ),
        ),
        patch(
            "app.application.create_booking_flow.read_only.get_shop",
            new=AsyncMock(return_value={"shop_id": "shop-1", "name": "東京中央店"}),
        ),
        patch(
            "app.application.create_booking_flow.read_only.list_courses",
            new=AsyncMock(
                return_value=[
                    {
                        "course_id": "course-1",
                        "name": "全身マッサージ",
                        "duration_minutes": 60,
                        "price": "5000",
                        "course_type": "main",
                    }
                ]
            ),
        ),
        patch(
            "app.application.create_booking_flow.read_only.get_available_slots",
            new=AsyncMock(return_value=available_slots),
        ),
        patch(
            "app.application.create_booking_flow.read_only.check_eligibility",
            new=AsyncMock(return_value={"eligible": True}),
        ),
    ):
        await flow.handle("conversation-1", create_nlu())
        await flow.handle(
            "conversation-1",
            create_nlu(),
            {"entity": "shop_id", "value": "shop-1"},
        )
        await flow.handle(
            "conversation-1",
            create_nlu(),
            {"entity": "main_course_id", "value": "course-1"},
        )
        await flow.handle(
            "conversation-1",
            create_nlu(),
            {"entity": "addon_course_ids", "value": []},
        )
        await flow.handle(
            "conversation-1",
            create_nlu(),
            {"entity": "number_of_people", "value": 2},
        )
        slot_response = await flow.handle(
            "conversation-1",
            create_nlu(),
            {"entity": "booking_date", "value": tomorrow},
        )
        assert slot_response["ui"]["options"][0]["id"] == "10:00"

        await flow.handle(
            "conversation-1",
            create_nlu(),
            {"entity": "start_time", "value": "10:00"},
        )
        summary = await flow.handle(
            "conversation-1",
            create_nlu(),
            {
                "entity": "customer",
                "value": {"name": "山田 太郎", "phone": "0901234567"},
            },
        )
        assert summary["ui"]["type"] == "booking_summary"
        assert summary["ui"]["data"]["confirmation_token"] == "ABC123DEF456"
        mutation.confirm.assert_not_awaited()

        result = await flow.handle(
            "conversation-1",
            create_nlu(),
            {"entity": "confirmation_token", "value": "ABC123DEF456"},
        )

    assert result["ui"]["type"] == "booking_result"
    assert result["data"]["booking_id"] == "booking-1"
    mutation.confirm.assert_awaited_once_with(
        "conversation-1",
        "ABC123DEF456",
    )
    assert store.states["conversation-1"].step is ConversationStep.COMPLETED
