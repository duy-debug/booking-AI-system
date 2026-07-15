# API endpoints cho RAG chat — POST /api/chat + POST /api/kb/seed

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from starlette.responses import StreamingResponse

from app.core.auth import get_current_admin
from app.core.exceptions import AppError
from app.db.session import get_db
from app.rag.chain import generate_response, generate_stream
from app.rag.ingestion import seed_all_docs
from app.rag.vector_store import count_chunks

router = APIRouter(tags=["rag"])


class ChatInput(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    stream: bool = False


class ChatOutput(BaseModel):
    answer: str


class SeedOutput(BaseModel):
    message: str
    stats: dict


@router.post("/api/chat")
def chat(body: ChatInput, db: Session = Depends(get_db)):
    # Chat với AI tư vấn massage — hỗ trợ streaming qua SSE
    # Kiểm tra KB có dữ liệu không
    if count_chunks(db) == 0:
        raise AppError(
            status_code=503,
            code="KNOWLEDGE_BASE_EMPTY",
            detail="KB chưa được seed dữ liệu. Admin chạy POST /api/kb/seed trước.",
        )

    if body.stream:
        # Streaming response (Server-Sent Events)
        return StreamingResponse(
            generate_stream(db, body.query),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    answer = generate_response(db, body.query)
    return {"answer": answer}


@router.post("/api/kb/seed", dependencies=[Depends(get_current_admin)])
def seed_knowledge_base(db: Session = Depends(get_db)):
    # Seed KB từ file docs/ — yêu cầu admin token
    stats = seed_all_docs(db)
    return SeedOutput(
        message="Seed KB thành công.",
        stats=stats,
    )


@router.get("/api/kb/stats")
def kb_stats(db: Session = Depends(get_db)):
    # Trả về thống kê KB (public, không cần auth)
    total = count_chunks(db)
    return {"total_chunks": total}
