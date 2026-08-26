# Repository cho CustomerRestriction — CRUD + tìm restriction active theo số điện thoại
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.customer import Customer
from app.db.models.customer_restriction import CustomerRestriction


class RestrictionRepository:
    # Khởi tạo với session database
    def __init__(self, session: Session):
        self.session = session

    # Tìm restriction theo ID
    def find_by_id(self, restriction_id: UUID) -> CustomerRestriction | None:
        return self.session.get(CustomerRestriction, restriction_id)

    # Danh sách restriction — lọc theo phone và trạng thái active
    def find_all(
        self,
        phone: str | None = None,
        is_active: bool | None = None,
    ) -> list[CustomerRestriction]:
        stmt = select(CustomerRestriction)
        if phone is not None:
            stmt = stmt.where(CustomerRestriction.phone == phone)
        if is_active is not None:
            stmt = stmt.where(CustomerRestriction.is_active == is_active)
        stmt = stmt.order_by(CustomerRestriction.created_at.desc())
        return list(self.session.scalars(stmt).all())

    # Restriction đang active của một số điện thoại
    def find_active_by_phone(self, phone: str) -> CustomerRestriction | None:
        stmt = select(CustomerRestriction).where(
            CustomerRestriction.phone == phone,
            CustomerRestriction.is_active == True,
        )
        return self.session.scalar(stmt)

    # Ưu tiên restriction theo customer_id; nếu dữ liệu cũ chưa có FK thì fallback về phone.
    def find_active_for_customer(
        self,
        *,
        customer_id: UUID | None,
        phone: str,
    ) -> CustomerRestriction | None:
        if customer_id is not None:
            stmt = select(CustomerRestriction).where(
                CustomerRestriction.customer_id == customer_id,
                CustomerRestriction.is_active == True,
            )
            restriction = self.session.scalar(stmt)
            if restriction is not None:
                return restriction

        return self.find_active_by_phone(phone)

    # Lấy customer_id cho restriction mới nếu customer đã tồn tại; không tạo customer giả.
    def find_customer_id_by_phone(self, phone: str) -> UUID | None:
        stmt = select(Customer.customer_id).where(Customer.phone == phone)
        return self.session.scalar(stmt)

    # Lưu restriction mới — add + flush
    def save(self, restriction: CustomerRestriction) -> CustomerRestriction:
        self.session.add(restriction)
        self.session.flush()
        return restriction

    # Làm mới entity từ database sau commit để lấy timestamp và giá trị do database sinh.
    def refresh(self, restriction: CustomerRestriction) -> CustomerRestriction:
        self.session.refresh(restriction)
        return restriction
