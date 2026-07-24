from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.schemas import ChatRequest, ChatResponse
from app.application.orchestrator import ConversationOrchestrator, build_orchestrator

router = APIRouter(prefix="/api", tags=["chat"])


# Khởi tạo orchestrator tại API composition root, không đưa Depends vào application.
def get_orchestrator() -> ConversationOrchestrator:
    return build_orchestrator()


# Nhận câu hỏi, điều phối qua application service và trả response có schema ổn định.
@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    orchestrator: Annotated[
        ConversationOrchestrator,
        Depends(get_orchestrator),
    ],
) -> ChatResponse:
    selection = body.selection.model_dump() if body.selection else None
    result = await orchestrator.handle(
        query=body.query,
        conversation_id=body.conversation_id,
        selection=selection,
    )
    return ChatResponse.model_validate(result)
