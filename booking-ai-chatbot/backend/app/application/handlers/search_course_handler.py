"""Resolve POS courses and add-ons for one shop."""

import unicodedata
from uuid import UUID

from app.domain.booking_models import BookingGateway, CourseSearchRequest, CourseType
from app.domain.outcomes import HandlerOutcome, HandlerResult


class SearchCourseHandler:
    """Loads and resolves courses without inventing catalog data."""

    # Nhận gateway POS để tải course/add-on theo từng shop.
    def __init__(self, booking_gateway: BookingGateway) -> None:
        self._booking_gateway = booking_gateway

    # Tìm liệu trình/add-on theo query, ưu tiên exact match trước substring match.
    async def execute(
        self,
        shop_id: UUID,
        query: str | None = None,
        *,
        course_type: CourseType | None = None,
        is_active: bool = True,
    ) -> HandlerResult:
        courses = await self._booking_gateway.search_courses(
            CourseSearchRequest(shop_id, course_type, is_active)
        )
        normalized = _normalize(query) if query is not None else ""
        if not normalized:
            return HandlerResult(HandlerOutcome.SUCCESS, {"courses": tuple(courses)})
        exact = [course for course in courses if _normalize(course.name) == normalized]
        matched = exact or [course for course in courses if normalized in _normalize(course.name)]
        if not matched:
            return HandlerResult(HandlerOutcome.NOT_FOUND, error_code="course_not_found")
        if len(matched) > 1:
            return HandlerResult(
                HandlerOutcome.AMBIGUOUS,
                {"courses": tuple(matched)},
                error_code="course_ambiguous",
            )
        return HandlerResult(HandlerOutcome.SUCCESS, {"courses": tuple(matched)})


# Chuẩn hóa text tiếng Việt để matching course không phụ thuộc dấu/case.
def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.strip().casefold())
    normalized = "".join(
        character for character in decomposed if unicodedata.category(character) != "Mn"
    )
    return normalized.replace("đ", "d")
