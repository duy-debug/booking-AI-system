"""Application handler for checking booking availability."""

from datetime import date, time
from uuid import UUID

from app.application.ports.booking_gateway import BookingGateway


class CheckAvailabilityHandler:
    """Coordinates the availability check use case."""

    def __init__(self, booking_gateway: BookingGateway) -> None:
        self._booking_gateway = booking_gateway

    async def execute(
        self,
        shop_id: UUID,
        service_id: UUID,
        booking_date: date,
    ) -> list[time]:
        """Return available times reported by the booking gateway."""
        return await self._booking_gateway.check_availability(
            shop_id=shop_id,
            service_id=service_id,
            booking_date=booking_date,
        )
