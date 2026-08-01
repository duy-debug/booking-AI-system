"""Application handler for searching a shop's service catalog."""

from uuid import UUID

from app.application.ports.booking_gateway import BookingGateway, CourseSearchRequest
from app.domain.booking import CourseType, Service


class SearchServiceHandler:
    """Coordinates the service search use case for a shop."""

    def __init__(self, booking_gateway: BookingGateway) -> None:
        self._booking_gateway = booking_gateway

    async def execute(
        self,
        shop_id: UUID,
        query: str | None = None,
        *,
        course_type: CourseType | None = None,
        is_active: bool = True,
    ) -> list[Service]:
        """Return the POS catalog, optionally filtered locally by course name."""
        services = await self._booking_gateway.search_services(
            CourseSearchRequest(
                shop_id=shop_id,
                course_type=course_type,
                is_active=is_active,
            )
        )
        normalized_query = query.strip().casefold() if query is not None else ""
        if not normalized_query:
            return services
        return [
            service
            for service in services
            if normalized_query in service.name.casefold()
        ]
