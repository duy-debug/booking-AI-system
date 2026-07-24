from app.domain.nlu import NLUResult
from app.rag.chain import answer_faq


class FAQHandler:
    # Trả lời FAQ từ context Qdrant đã grounded, không dùng dữ liệu động do LLM tạo.
    async def handle(self, query: str, _nlu: NLUResult, _conversation_id: str) -> dict:
        return {"answer": await answer_faq(query)}
