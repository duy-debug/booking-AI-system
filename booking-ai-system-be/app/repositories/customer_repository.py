# Repository cho Customer — CRUD + tìm theo số điện thoại
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.customer import Customer


class CustomerRepository:
    # Khởi tạo với session database
    def __init__(self, session: Session):
        self.session = session

    # Tìm customer theo ID
    def find_by_id(self, customer_id: UUID) -> Customer | None:
        return self.session.get(Customer, customer_id)

    # Tìm customer theo số điện thoại
    def find_by_phone(self, phone: str) -> Customer | None:
        stmt = select(Customer).where(Customer.phone == phone)
        return self.session.scalar(stmt)

    # Lưu customer mới — add + flush
    def save(self, customer: Customer) -> Customer:
        self.session.add(customer)
        self.session.flush()
        return customer
