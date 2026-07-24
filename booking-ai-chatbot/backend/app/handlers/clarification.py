from app.domain.nlu import NLUResult


class ClarificationHandler:
    # Yêu cầu khách hàng diễn đạt lại khi intent hoặc entity chưa đủ chắc chắn.
    async def handle(self, _query: str, _nlu: NLUResult, _conversation_id: str) -> dict:
        return {
            "answer": (
                "Tôi chưa hiểu rõ yêu cầu. Bạn muốn xem dịch vụ, kiểm tra giờ trống, "
                "đặt lịch, đổi lịch hay hủy lịch?"
            )
        }
