# POS Client factory — trả về mock hoặc real client dựa trên config

from app.core.config import settings
from app.integrations.pos.base import AbstractPOSClient
from app.integrations.pos.mock import MockPOSClient


def get_pos_client() -> AbstractPOSClient:
    # Factory: trả về MockPOSClient nếu POS_MODE=mock, ngược lại RealPOSClient
    if settings.POS_MODE == "real":
        from app.integrations.pos.real import RealPOSClient

        return RealPOSClient(
            base_url=settings.POS_BASE_URL,
            api_key=settings.POS_API_KEY,
        )
    return MockPOSClient()
