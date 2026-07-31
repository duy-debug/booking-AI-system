"""Application handler for customer lookup and NG-list verification."""

from app.application.exceptions import CustomerVerificationMismatchError
from app.application.ports.booking_gateway import (
    BookingGateway,
    CustomerVerificationResult,
)
from app.domain.booking import Customer
from app.domain.booking_context import BookingContext
from app.domain.booking_rules import BookingRules


class CollectCustomerHandler:
    """Collects a phone and stores authoritative customer verification."""

    def __init__(self, booking_gateway: BookingGateway) -> None:
        self._booking_gateway = booking_gateway

    async def execute(
        self,
        context: BookingContext,
        phone: str,
        name: str | None = None,
    ) -> CustomerVerificationResult:
        """Validate a phone, verify it through POS and update the context."""
        BookingRules.validate_phone(phone)
        normalized_phone = "".join(phone.split()).replace("-", "")
        normalized_name = name.strip() or None if name is not None else None

        context.set_phone(normalized_phone)
        context.customer = None
        result = await self._booking_gateway.verify_customer(normalized_phone)
        if result.phone != normalized_phone:
            raise CustomerVerificationMismatchError(
                "Customer verification returned a different phone."
            )

        context.customer = Customer(phone=normalized_phone, name=normalized_name)
        if result.ng_list_checked:
            context.set_customer_verification(
                member_rank=result.member_rank,
                is_ng_customer=result.is_ng_customer,
            )
        else:
            context.member_rank = result.member_rank
            context.ng_list_checked = False
            context.is_ng_customer = result.is_ng_customer
        return result
