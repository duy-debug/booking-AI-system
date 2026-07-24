import json
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import AppError
from app.domain.state import ConversationState, ConversationStep
from app.integrations.redis import RedisConversationStore


@pytest.mark.asyncio
async def test_save_state_increments_version_after_atomic_success():
    client = AsyncMock()
    client.eval.return_value = 1
    store = RedisConversationStore(client=client)
    state = ConversationState(
        conversation_id="conversation-1",
        intent="create_booking",
    )

    await store.save_state(state)

    assert state.version == 1
    client.eval.assert_awaited_once()


@pytest.mark.asyncio
async def test_save_state_rejects_concurrent_update():
    client = AsyncMock()
    client.eval.return_value = 0
    store = RedisConversationStore(client=client)
    state = ConversationState(
        conversation_id="conversation-1",
        version=2,
    )

    with pytest.raises(AppError) as exc:
        await store.save_state(state)

    assert exc.value.code == "CONVERSATION_STATE_CONFLICT"
    assert state.version == 2


@pytest.mark.asyncio
async def test_get_state_restores_domain_model():
    client = AsyncMock()
    client.get.return_value = json.dumps(
        {
            "conversation_id": "conversation-1",
            "intent": "create_booking",
            "step": "collect_service",
            "entities": {"shop_id": "shop-1"},
            "version": 3,
        }
    )
    store = RedisConversationStore(client=client)

    state = await store.get_state("conversation-1")

    assert state.step is ConversationStep.COLLECT_SERVICE
    assert state.entities["shop_id"] == "shop-1"
    assert state.version == 3
