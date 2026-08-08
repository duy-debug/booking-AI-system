"""Atomically validate, look up and confirm booking customers."""

from copy import deepcopy

from app.domain.booking_context import BookingContext
from app.domain.booking_models import (
    BookingContextNotReadyError,
    BookingGateway,
    BookingRules,
    Customer,
    CustomerNotAllowedError,
    CustomerVerificationMismatchError,
    CustomerVerificationRequest,
    InvalidBookingDataError,
)
from app.domain.outcomes import HandlerOutcome, HandlerResult


class CheckCustomerHandler:
    """Coordinates customer verification without partial mutation on failures."""

    # Nhận gateway POS để kiểm tra blacklist/customer record theo số điện thoại.
    def __init__(
        self,
        booking_gateway: BookingGateway,
    ) -> None:
        self._booking_gateway = booking_gateway

    # Kiểm tra phone trên POS, phân biệt khách bị chặn, khách cũ và khách mới cần tên.
    async def check(
        self,
        context: BookingContext,
        phone: str,
        name: str | None = None,
    ) -> HandlerResult:
        candidate = deepcopy(context)
        try:
            if candidate.shop is None:
                raise BookingContextNotReadyError(
                    "A shop is required before customer verification."
                )
            BookingRules.validate_phone(phone)
            normalized_phone = "".join(phone.split()).replace("-", "")
            normalized_name = name.strip() or None if name is not None else None
            candidate.set_phone(normalized_phone)
            candidate.customer = None
            try:
                verification = await self._booking_gateway.verify_customer(
                    CustomerVerificationRequest(
                        shop_id=candidate.shop.shop_id,
                        phone=normalized_phone,
                    )
                )
            except CustomerNotAllowedError:
                candidate.customer = Customer(
                    phone=normalized_phone,
                    name=normalized_name,
                )
                candidate.set_customer_verification(
                    member_rank=None,
                    is_ng_customer=True,
                )
                raise
            if verification.phone != normalized_phone:
                raise CustomerVerificationMismatchError(
                    "Customer verification returned a different phone."
                )
            authoritative_name = (
                verification.customer_name or normalized_name
                if verification.customer_id is not None
                else normalized_name
            )
            candidate.customer_id = verification.customer_id
            candidate.customer = Customer(
                phone=normalized_phone,
                name=authoritative_name,
            )
            if verification.ng_list_checked:
                candidate.set_customer_verification(
                    member_rank=verification.member_rank,
                    is_ng_customer=verification.is_ng_customer,
                )
            else:
                candidate.member_rank = verification.member_rank
                candidate.ng_list_checked = False
                candidate.is_ng_customer = verification.is_ng_customer
        except CustomerNotAllowedError:
            return HandlerResult(HandlerOutcome.BLOCKED, error_code="customer_ng_blocked")
        except InvalidBookingDataError as error:
            return HandlerResult(
                HandlerOutcome.INVALID_INPUT,
                error_code=type(error).__name__,
            )
        except CustomerVerificationMismatchError:
            return HandlerResult(
                HandlerOutcome.EXTERNAL_FAILURE,
                error_code="customer_verification_mismatch",
            )
        except Exception:
            return HandlerResult(
                HandlerOutcome.EXTERNAL_FAILURE,
                error_code="customer_verification_unavailable",
            )
        updates = {
            "phone": candidate.phone,
            "customer": candidate.customer,
            "customer_id": candidate.customer_id,
            "member_rank": candidate.member_rank,
            "ng_list_checked": candidate.ng_list_checked,
            "is_ng_customer": candidate.is_ng_customer,
        }
        return HandlerResult(
            HandlerOutcome.SUCCESS,
            {"verification": verification},
            updates,
        )

    # Xác nhận phone đã qua bước check trước đó và cập nhật context confirmation.
    def confirm(self, context: BookingContext) -> HandlerResult:
        if context.phone is None:
            return HandlerResult(
                HandlerOutcome.INVALID_INPUT,
                error_code="phone_required",
            )
        return HandlerResult(
            HandlerOutcome.SUCCESS,
            context_updates={"phone_confirmed": True},
        )
