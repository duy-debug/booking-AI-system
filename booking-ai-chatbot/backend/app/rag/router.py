from fastapi import APIRouter, Header

from app.core.config import settings
from app.core.exceptions import AppError
from app.rag.ingestion import seed_all_docs
from app.rag.vector_store import count_chunks

router = APIRouter(prefix="/api/kb", tags=["knowledge-base"])


# Xác thực API quản trị knowledge base bằng Bearer key riêng.
def _require_admin(authorization: str | None) -> None:
    expected = f"Bearer {settings.ADMIN_API_KEY}"
    if not authorization or authorization != expected:
        raise AppError(
            401,
            code="UNAUTHORIZED",
            detail="Admin API key không hợp lệ.",
        )


# Seed lại tài liệu trong thư mục docs vào Qdrant.
@router.post("/seed")
async def seed_knowledge_base(authorization: str | None = Header(None)) -> dict:
    _require_admin(authorization)
    stats = await seed_all_docs()
    return {"stats": stats}


# Trả số lượng chunk hiện có để kiểm tra trạng thái knowledge base.
@router.get("/stats")
async def knowledge_base_stats(authorization: str | None = Header(None)) -> dict:
    _require_admin(authorization)
    return {"total_chunks": await count_chunks()}
