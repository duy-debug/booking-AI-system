from unittest.mock import AsyncMock

import pytest

from app.application.booking_workflow import BookingWorkflow
from app.core.exceptions import AppError


class MemoryStore:
    def __init__(self):
        self.pending = None

    # Lưu pending action trong bộ nhớ để test application mà không cần Redis thật.
    async def save_pending(self, action):
        self.pending = action

    # Trả pending action hiện tại cho bước xác nhận.
    async def get_pending(self, _conversation_id):
        return self.pending

    # Xóa pending action sau mutation thành công.
    async def delete_pending(self, _conversation_id):
        self.pending = None


@pytest.mark.asyncio
async def test_create_uses_stable_idempotency_key():
    gateway = AsyncMock()
    gateway.create_booking.return_value = {"booking_id": "b1"}
    store = MemoryStore()
    workflow = BookingWorkflow(gateway, store)

    pending = await workflow.prepare("c1", "create_booking", {"shop_id": "s1"})
    result = await workflow.confirm("c1", pending.confirmation_token)

    assert result == {"booking_id": "b1"}
    gateway.create_booking.assert_awaited_once()
    assert gateway.create_booking.await_args.args[1]
    assert store.pending is None


@pytest.mark.asyncio
async def test_wrong_confirmation_token_keeps_pending_action():
    gateway = AsyncMock()
    store = MemoryStore()
    workflow = BookingWorkflow(gateway, store)
    await workflow.prepare("c1", "cancel_booking", {"booking_id": "b1"})

    with pytest.raises(AppError) as exc:
        await workflow.confirm("c1", "WRONG")

    assert exc.value.code == "INVALID_CONFIRMATION_TOKEN"
    assert store.pending is not None
    gateway.update_booking.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_backend_call_keeps_pending_for_safe_retry():
    gateway = AsyncMock()
    gateway.update_booking.side_effect = AppError(
        409, code="SLOT_CONFLICT", detail="Slot không còn khả dụng."
    )
    store = MemoryStore()
    workflow = BookingWorkflow(gateway, store)
    pending = await workflow.prepare(
        "c1",
        "update_booking",
        {"booking_id": "b1", "start_time": "10:00"},
    )

    with pytest.raises(AppError):
        await workflow.confirm("c1", pending.confirmation_token)

    assert store.pending is not None
