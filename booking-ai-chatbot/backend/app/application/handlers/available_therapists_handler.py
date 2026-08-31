"""Application handler for loading therapists available in the selected slot."""

from datetime import datetime, timedelta

from app.domain.booking_context import BookingContext
from app.domain.booking_models import (
    AvailableTherapistRequest,
    TherapistAvailabilityGateway,
    TherapistPreference,
)


# Use case đọc danh sách kỹ thuật viên còn trống cho slot đã chọn.
class AvailableTherapistsHandler:
    """Loads available therapists without mutating dialog context."""

    # Nhận gateway availability từ composition root để controller không gọi POS trực tiếp.
    def __init__(self, therapist_gateway: TherapistAvailabilityGateway) -> None:
        self._therapist_gateway = therapist_gateway

    # Chỉ trả danh sách khi context đã đủ shop/date/time/duration cho single booking.
    async def execute(self, context: BookingContext) -> tuple[TherapistPreference, ...]:
        if (
            context.shop is None
            or context.booking_date is None
            or context.start_time is None
            or context.total_duration_minutes is None
        ):
            return ()

        end_time = (
            datetime.combine(context.booking_date, context.start_time)
            + timedelta(minutes=context.total_duration_minutes)
        ).time()
        therapists = await self._therapist_gateway.search_available_therapists(
            AvailableTherapistRequest(
                shop_id=context.shop.shop_id,
                booking_date=context.booking_date,
                start_time=context.start_time,
                end_time=end_time,
            )
        )
        return tuple(therapists)
