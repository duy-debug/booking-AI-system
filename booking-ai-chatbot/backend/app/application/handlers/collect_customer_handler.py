"""Application handler for customer lookup and NG-list verification."""

from app.application.exceptions import CustomerVerificationMismatchError
from app.application.ports.booking_gateway import (
    BookingGateway,
    CustomerVerificationRequest,
    CustomerVerificationResult,
)
from app.domain.booking import Customer
from app.domain.booking_context import BookingContext
from app.domain.booking_rules import BookingRules
from app.domain.exceptions import BookingContextNotReadyError, CustomerNotAllowedError


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
        if context.shop is None:
            raise BookingContextNotReadyError(
                "A shop is required before customer verification."
            )
        BookingRules.validate_phone(phone)
        normalized_phone = "".join(phone.split()).replace("-", "")
        normalized_name = name.strip() or None if name is not None else None

        context.set_phone(normalized_phone)
        context.customer = None
        request = CustomerVerificationRequest(
            shop_id=context.shop.shop_id,
            phone=normalized_phone,
        )
        try:
            result = await self._booking_gateway.verify_customer(request)
        except CustomerNotAllowedError:
            context.customer = Customer(phone=normalized_phone, name=normalized_name)
            context.set_customer_verification(
                member_rank=None,
                visit_count=None,
                is_ng_customer=True,
            )
            raise
        if result.phone != normalized_phone:
            raise CustomerVerificationMismatchError(
                "Customer verification returned a different phone."
            )

        authoritative_name = (
            result.customer_name or normalized_name
            if result.customer_id is not None
            else normalized_name
        )
        context.customer_id = result.customer_id
        context.customer = Customer(phone=normalized_phone, name=authoritative_name)
        if result.ng_list_checked:
            context.set_customer_verification(
                member_rank=result.member_rank,
                visit_count=result.visit_count,
                is_ng_customer=result.is_ng_customer,
            )
        else:
            context.member_rank = result.member_rank
            context.visit_count = result.visit_count
            context.ng_list_checked = False
            context.is_ng_customer = result.is_ng_customer
        return result
