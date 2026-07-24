from __future__ import annotations

import json
from datetime import datetime

from redis.asyncio import Redis

from app.core.config import settings
from app.core.exceptions import AppError
from app.domain.models import PendingAction
from app.domain.state import ConversationState

_store: "RedisConversationStore | None" = None

SAVE_STATE_SCRIPT = """
local current = redis.call('GET', KEYS[1])
local expected_version = tonumber(ARGV[1])

if current then
    local decoded = cjson.decode(current)
    local current_version = tonumber(decoded['version'] or 0)
    if current_version ~= expected_version then
        return 0
    end
elseif expected_version ~= 0 then
    return 0
end

redis.call('SET', KEYS[1], ARGV[2], 'EX', ARGV[3])
return 1
"""


class RedisConversationStore:
    # Cho phép inject Redis mock khi test và dùng Redis URL cấu hình khi chạy thật.
    def __init__(self, client: Redis | None = None) -> None:
        self._client = client or Redis.from_url(settings.REDIS_URL, decode_responses=True)

    # Tạo key có namespace để state chatbot không trùng dữ liệu Redis khác.
    @staticmethod
    def _pending_key(conversation_id: str) -> str:
        return f"chatbot:pending:{conversation_id}"

    # Tạo key riêng cho state để state hội thoại và pending mutation có TTL độc lập.
    @staticmethod
    def _state_key(conversation_id: str) -> str:
        return f"chatbot:conversation:{conversation_id}"

    # Lưu state bằng optimistic concurrency để hai request không ghi đè lẫn nhau.
    async def save_state(self, state: ConversationState) -> None:
        expected_version = state.version
        serialized = state.to_dict()
        serialized["version"] = expected_version + 1
        saved = await self._client.eval(
            SAVE_STATE_SCRIPT,
            1,
            self._state_key(state.conversation_id),
            expected_version,
            json.dumps(serialized, ensure_ascii=False),
            settings.CONVERSATION_TTL_SECONDS,
        )
        if int(saved) != 1:
            raise AppError(
                409,
                code="CONVERSATION_STATE_CONFLICT",
                detail="Hội thoại vừa được cập nhật bởi một request khác. Vui lòng thử lại.",
            )
        state.version = expected_version + 1

    # Lấy state từ Redis hoặc trả state rỗng khi khách hàng bắt đầu hội thoại mới.
    async def get_state(self, conversation_id: str) -> ConversationState:
        value = await self._client.get(self._state_key(conversation_id))
        if not value:
            return ConversationState(conversation_id=conversation_id)
        return ConversationState.from_dict(json.loads(value))

    # Xóa state khi workflow kết thúc hoặc người dùng chủ động hủy hội thoại.
    async def delete_state(self, conversation_id: str) -> None:
        await self._client.delete(self._state_key(conversation_id))

    # Lưu bản chụp mutation với TTL để dữ liệu khách hàng không tồn tại vô hạn.
    async def save_pending(self, action: PendingAction) -> None:
        value = json.dumps(
            {
                "conversation_id": action.conversation_id,
                "action": action.action,
                "payload": action.payload,
                "confirmation_token": action.confirmation_token,
                "expires_at": action.expires_at.isoformat(),
            },
            ensure_ascii=False,
        )
        await self._client.set(
            self._pending_key(action.conversation_id),
            value,
            ex=settings.CONVERSATION_TTL_SECONDS,
        )

    # Đọc pending action còn hạn; tự dọn state nếu thời gian xác nhận đã hết.
    async def get_pending(self, conversation_id: str) -> PendingAction | None:
        value = await self._client.get(self._pending_key(conversation_id))
        if not value:
            return None
        data = json.loads(value)
        action = PendingAction(
            conversation_id=data["conversation_id"],
            action=data["action"],
            payload=data["payload"],
            confirmation_token=data["confirmation_token"],
            expires_at=datetime.fromisoformat(data["expires_at"]),
        )
        if action.is_expired():
            await self.delete_pending(conversation_id)
            return None
        return action

    # Xóa pending action sau khi mutation hoàn tất.
    async def delete_pending(self, conversation_id: str) -> None:
        await self._client.delete(self._pending_key(conversation_id))

    # Đóng Redis connection pool khi ứng dụng shutdown.
    async def close(self) -> None:
        await self._client.aclose()


# Khởi tạo một Redis store dùng chung để tránh tạo connection pool ở mỗi request.
def get_conversation_store() -> RedisConversationStore:
    global _store
    if _store is None:
        _store = RedisConversationStore()
    return _store


# Đóng connection pool dùng chung trong FastAPI shutdown lifecycle.
async def close_redis() -> None:
    global _store
    if _store is not None:
        await _store.close()
        _store = None
