import uuid

# Service kiểm tra điều kiện đặt lịch — NG list, trạng thái shop, lịch sử khách hàng
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.repositories import ShopRepository, RestrictionRepository, CustomerRepository
from app.schemas.booking import BookingEligibilityCheckResponse


class EligibilityService:
    # Khởi tạo với session và repository
    def __init__(self, session: Session):
        self.session = session
        self.shop_repo = ShopRepository(session)
        self.restriction_repo = RestrictionRepository(session)
        self.customer_repo = CustomerRepository(session)

    # Kiểm tra điều kiện đặt lịch — shop active, NG list, trả về thông tin khách hàng nếu đã có
    def check_eligibility(self, phone: str, shop_id: uuid.UUID) -> dict:
        shop = self.shop_repo.find_by_id(shop_id)
        if not shop:
            raise AppError(404, code="SHOP_NOT_FOUND", detail="Không tìm thấy shop")
        if not shop.is_active:
            raise AppError(422, code="SHOP_INACTIVE", detail="Shop không hoạt động")

        restriction = self.restriction_repo.find_active_by_phone(phone)
        if restriction:
            raise AppError(403, code="CUSTOMER_IN_NG_LIST", detail="Số điện thoại này không được phép đặt booking")

        customer = self.customer_repo.find_by_phone(phone)
        customer_data = None
        if customer:
            customer_data = {
                "customer_type": "existing",
                "customer_id": str(customer.customer_id),
                "name": customer.name,
                "is_member": customer.is_member,
                "member_rank": customer.member_rank,
                "visit_count": customer.visit_count,
            }

        return BookingEligibilityCheckResponse(
            check_id=uuid.uuid4(),
            phone=phone,
            eligible=True,
            customer=customer_data,
            restriction=None,
        ).model_dump(mode="json")
