from typing import Any, Protocol

from app.domain.models import PendingAction
from app.domain.state import ConversationState


class BookingGateway(Protocol):
    # Định nghĩa thao tác tạo booking mà application được phép gọi.
    async def create_booking(
        self, payload: dict[str, Any], idempotency_key: str
    ) -> dict[str, Any]: ...

    # Định nghĩa thao tác cập nhật booking mà application được phép gọi.
    async def update_booking(self, booking_id: str, payload: dict[str, Any]) -> dict[str, Any]: ...


class ConversationStore(Protocol):
    # Lưu state hội thoại sau mỗi bước thu thập dữ liệu.
    async def save_state(self, state: ConversationState) -> None: ...

    # Lấy state hiện tại hoặc tạo state rỗng cho conversation mới.
    async def get_state(self, conversation_id: str) -> ConversationState: ...

    # Xóa state khi người dùng hủy luồng hoặc khi dữ liệu không còn cần thiết.
    async def delete_state(self, conversation_id: str) -> None: ...

    # Lưu mutation đang chờ khách hàng xác nhận.
    async def save_pending(self, action: PendingAction) -> None: ...

    # Đọc mutation đang chờ theo mã phiên hội thoại.
    async def get_pending(self, conversation_id: str) -> PendingAction | None: ...

    # Xóa mutation sau khi Booking Backend thực thi thành công.
    async def delete_pending(self, conversation_id: str) -> None: ...
