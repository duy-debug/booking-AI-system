from app.conversation.chain import answer_general
from app.domain.nlu import NLUResult


class ConversationHandler:
    async def handle(self, query: str, _nlu: NLUResult, _conversation_id: str) -> dict:
        return {"answer": await answer_general(query)}
