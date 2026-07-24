from qdrant_client import AsyncQdrantClient

from app.core.config import settings

_client: AsyncQdrantClient | None = None


# Khởi tạo Qdrant client dùng chung cho vòng đời ứng dụng.
async def init_qdrant() -> AsyncQdrantClient:
    global _client
    if _client is None:
        _client = AsyncQdrantClient(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT,
        )
    return _client


# Trả Qdrant client hiện tại và tự khởi tạo khi cần.
async def get_qdrant() -> AsyncQdrantClient:
    return await init_qdrant()


# Đóng Qdrant client khi ứng dụng dừng.
async def close_qdrant() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None
