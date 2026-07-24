from app.domain.intent import Intent
from app.domain.nlu import NLUResult
from app.tools import read_only


class InformationHandler:
    # Đọc dữ liệu động từ Booking Backend dựa trên resource đã được router xác nhận.
    async def handle(self, _query: str, nlu: NLUResult, _conversation_id: str) -> dict:
        if nlu.intent is Intent.SHOP_INFO:
            shops = await read_only.list_shops()
            if not shops:
                return {"answer": "Hiện chưa có cửa hàng đang hoạt động.", "data": []}
            names = ", ".join(str(shop.get("name", "")) for shop in shops)
            return {
                "answer": f"Các cửa hàng đang hoạt động: {names}.",
                "data": shops,
            }
        if nlu.intent is Intent.COURSE_INFO:
            return {
                "answer": "Bạn muốn xem dịch vụ của cửa hàng nào?",
                "missing_entities": ["shop_id"],
            }
        return {
            "answer": ("Vui lòng cung cấp cửa hàng, dịch vụ, ngày và giờ để kiểm tra slot."),
            "missing_entities": [
                "shop_id",
                "main_course_id",
                "booking_date",
                "start_time",
            ],
        }
