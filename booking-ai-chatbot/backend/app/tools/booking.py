from __future__ import annotations

import re
from typing import Any
from uuid import uuid4

from app.domain.models import PendingAction
from app.integrations import booking_api

_pending_actions: dict[str, PendingAction] = {}


# Lưu pending action tương thích với API cũ; production workflow sử dụng Redis store.
def set_pending(conversation_id: str, action: str, payload: dict[str, Any]) -> PendingAction:
    pending = PendingAction(
        conversation_id=conversation_id,
        action=action,
        payload=dict(payload),
    )
    _pending_actions[conversation_id] = pending
    return pending


# Lấy pending action còn hạn và tự loại bỏ dữ liệu đã hết hạn.
def get_pending(conversation_id: str) -> PendingAction | None:
    pending = _pending_actions.get(conversation_id)
    if pending and pending.is_expired():
        _pending_actions.pop(conversation_id, None)
        return None
    return pending


# Lấy rồi xóa pending action nếu confirmation token hợp lệ.
def pop_pending(conversation_id: str, token: str | None = None) -> PendingAction | None:
    pending = get_pending(conversation_id)
    if pending is None:
        return None
    if token is not None and token.upper() != pending.confirmation_token:
        return None
    return _pending_actions.pop(conversation_id, None)


# Nhận diện câu xác nhận hoặc từ chối và trích xuất confirmation token nếu có.
def check_confirmation_intent(message: str) -> tuple[bool, str | None]:
    normalized = message.strip().lower()
    token_match = re.search(r"\b([A-F0-9]{12})\b", message.upper())
    token = token_match.group(1) if token_match else None
    accepted = normalized in {"có", "co", "yes", "ok", "xác nhận", "xac nhan"}
    return accepted or token is not None, token


# Kiểm tra eligibility rồi tạo pending action, chưa gọi API tạo booking.
async def initiate_create_booking(conversation_id: str, payload: dict[str, Any]) -> str:
    customer = payload.get("customer") or {}
    await booking_api.check_eligibility(
        phone=str(customer.get("phone", "")),
        shop_id=str(payload.get("shop_id", "")),
    )
    prepared = dict(payload)
    prepared.setdefault("_idempotency_key", str(uuid4()))
    pending = set_pending(conversation_id, "create_booking", prepared)
    return (
        "Vui lòng xác nhận tạo booking bằng mã "
        f"{pending.confirmation_token}. Mã có hiệu lực trong 10 phút."
    )


# Thực thi tạo booking đúng một lần sau khi pending action được xác nhận.
async def confirm_create_booking(conversation_id: str, token: str | None = None) -> str:
    pending = pop_pending(conversation_id, token)
    if pending is None or pending.action != "create_booking":
        return "Không tìm thấy yêu cầu tạo booking hợp lệ đang chờ xác nhận."
    result = await booking_api.create_booking(dict(pending.payload))
    booking_id = result.get("booking_id", "")
    return f"Đặt lịch thành công. Mã booking: {booking_id}"


# Tạo pending action hủy booking để khách hàng kiểm tra trước khi mutation.
async def initiate_cancel_booking(conversation_id: str, payload: dict[str, Any]) -> str:
    pending = set_pending(conversation_id, "cancel_booking", payload)
    return (
        "Vui lòng xác nhận hủy booking bằng mã "
        f"{pending.confirmation_token}. Mã có hiệu lực trong 10 phút."
    )


# Gọi Public Booking API để hủy sau khi xác nhận hợp lệ.
async def cancel_confirmed_booking(conversation_id: str, token: str | None = None) -> str:
    pending = pop_pending(conversation_id, token)
    if pending is None or pending.action != "cancel_booking":
        return "Không tìm thấy yêu cầu hủy booking hợp lệ đang chờ xác nhận."
    booking_id = str(pending.payload["booking_id"])
    reason = pending.payload.get("cancel_reason")
    await booking_api.cancel_booking(booking_id=booking_id, reason=reason)
    return "Hủy booking thành công."
