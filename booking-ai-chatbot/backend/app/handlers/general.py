from app.domain.nlu import NLUResult
from app.rag.chain import answer_faq


class GeneralHandler:
    # Xử lý hội thoại chung bằng cùng lớp grounded response để giữ hành vi an toàn.
    async def handle(self, query: str, _nlu: NLUResult, _conversation_id: str) -> dict:
        return {"answer": await answer_faq(query)}
