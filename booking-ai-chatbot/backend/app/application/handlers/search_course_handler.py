"""Resolve POS courses and add-ons for one shop."""

import unicodedata
from uuid import UUID

from app.domain.booking_models import BookingGateway, Course, CourseSearchRequest, CourseType
from app.domain.outcomes import HandlerOutcome, HandlerResult


class SearchCourseHandler:
    """Loads and resolves courses without inventing catalog data."""

    def __init__(self, booking_gateway: BookingGateway) -> None:
        self._booking_gateway = booking_gateway

    async def execute(
        self,
        shop_id: UUID,
        query: str | None = None,
        *,
        course_type: CourseType | None = None,
        is_active: bool = True,
    ) -> list[Course]:
        courses = await self._booking_gateway.search_courses(
            CourseSearchRequest(shop_id, course_type, is_active)
        )
        normalized = _normalize(query) if query is not None else ""
        if not normalized:
            return courses
        exact = [course for course in courses if _normalize(course.name) == normalized]
        return exact or [
            course for course in courses if normalized in _normalize(course.name)
        ]

    async def handle(
        self,
        shop_id: UUID,
        query: str | None = None,
        *,
        course_type: CourseType | None = None,
        duration_minutes: int | None = None,
        people_count: int | None = None,
    ) -> HandlerResult:
        if people_count is not None and not 1 <= people_count <= 3:
            return HandlerResult(
                HandlerOutcome.INVALID_INPUT,
                error_code="invalid_people_count",
            )
        try:
            courses = await self.execute(shop_id, query, course_type=course_type)
        except Exception:
            return HandlerResult(
                HandlerOutcome.EXTERNAL_FAILURE,
                error_code="course_lookup_unavailable",
            )
        compatible = [
            course
            for course in courses
            if duration_minutes is None or course.duration_minutes == duration_minutes
        ]
        if not compatible:
            return HandlerResult(HandlerOutcome.NOT_FOUND, error_code="course_not_found")
        if query and len(compatible) > 1:
            return HandlerResult(
                HandlerOutcome.AMBIGUOUS,
                {"courses": tuple(compatible)},
                error_code="course_ambiguous",
            )
        return HandlerResult(HandlerOutcome.SUCCESS, {"courses": tuple(compatible)})


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.strip().casefold())
    return "".join(
        character for character in decomposed if unicodedata.category(character) != "Mn"
    ).replace("đ", "d")
