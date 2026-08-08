"""Application handler for searching shops."""

import unicodedata
from dataclasses import dataclass
from uuid import UUID

from app.domain.booking_models import (
    AvailabilityRequest,
    BookingGateway,
    Course,
    CourseSearchRequest,
    CourseType,
    Shop,
    ShopSearchCriteria,
    ShopTherapist,
    TherapistAvailabilityGateway,
    TherapistCatalogGateway,
    TherapistPreference,
    TherapistPreferenceType,
)
from app.domain.outcomes import HandlerOutcome, HandlerResult


class SearchShopHandler:
    """Coordinates the shop search use case."""

    # Tải toàn bộ shop eligible từ POS rồi mới áp filter deterministic theo constraint đã biết.
    def __init__(
        self,
        booking_gateway: BookingGateway,
        *,
        therapist_catalog_gateway: TherapistCatalogGateway | None = None,
        therapist_availability_gateway: TherapistAvailabilityGateway | None = None,
    ) -> None:
        self._booking_gateway = booking_gateway
        self._therapist_catalog_gateway = therapist_catalog_gateway
        self._therapist_availability_gateway = therapist_availability_gateway

    # Tìm shop theo query và các constraint an toàn của bước chọn shop.
    async def execute(
        self,
        query: str | None = None,
        *,
        criteria: ShopSearchCriteria | None = None,
    ) -> HandlerResult:
        criteria = criteria or ShopSearchCriteria()
        shops = _unique_named_shops(await self._booking_gateway.search_shops())
        normalized_query = _normalized_optional(query)
        matched = [
            shop
            for shop in shops
            if normalized_query is None
            or normalized_query in _normalize_search_text(shop.name)
            or (
                shop.address is not None
                and normalized_query in _normalize_search_text(shop.address)
            )
        ]
        if not matched:
            return HandlerResult(HandlerOutcome.NOT_FOUND, error_code="shop_not_found")

        matching_shops = await self._filter_matching_shops(matched, criteria)
        if not matching_shops:
            return HandlerResult(
                HandlerOutcome.NOT_FOUND,
                error_code=_shop_match_failure_code(criteria),
            )
        return HandlerResult(HandlerOutcome.SUCCESS, {"shops": tuple(matching_shops)})

    # Chỉ dùng exact availability khi đã đủ full booking shape; nếu chưa đủ thì chỉ lọc capability.
    async def _filter_matching_shops(
        self,
        shops: list[Shop],
        criteria: ShopSearchCriteria,
    ) -> list[Shop]:
        service_name = _normalized_optional(criteria.requested_main_course_name)
        addon_name = _normalized_optional(criteria.requested_addon_name)
        therapist_name = _normalized_optional(criteria.requested_therapist_name)
        therapist_gender = _normalized_optional(criteria.requested_therapist_gender)

        if not any((service_name, addon_name, therapist_name, therapist_gender)):
            return shops

        if not _has_exact_availability_shape(criteria):
            return await self._filter_capability_only(
                shops,
                service_name=service_name,
                addon_name=addon_name,
                therapist_name=therapist_name,
                therapist_gender=therapist_gender,
            )

        exact_matches: list[Shop] = []
        for shop in shops:
            capability = await self._shop_capability(
                shop,
                service_name=service_name,
                addon_name=addon_name,
                therapist_name=therapist_name,
                therapist_gender=therapist_gender,
            )
            if not capability.matches:
                continue
            if await self._shop_matches_exact_availability(shop, capability, criteria):
                exact_matches.append(shop)
        return exact_matches

    # Filter ownership/service support mà không dùng dữ liệu giả cho availability.
    async def _filter_capability_only(
        self,
        shops: list[Shop],
        *,
        service_name: str | None,
        addon_name: str | None,
        therapist_name: str | None,
        therapist_gender: str | None,
    ) -> list[Shop]:
        matched: list[Shop] = []
        for shop in shops:
            capability = await self._shop_capability(
                shop,
                service_name=service_name,
                addon_name=addon_name,
                therapist_name=therapist_name,
                therapist_gender=therapist_gender,
            )
            if capability.matches:
                matched.append(shop)
        return matched

    # Đánh giá shop có service/add-on/therapist phù hợp hay không bằng dữ liệu authoritative.
    async def _shop_capability(
        self,
        shop: Shop,
        *,
        service_name: str | None,
        addon_name: str | None,
        therapist_name: str | None,
        therapist_gender: str | None,
    ) -> "_ShopCapability":
        main_courses: tuple[Course, ...] = ()
        addon_courses: tuple[Course, ...] = ()
        therapists: tuple[ShopTherapist, ...] = ()
        if service_name is not None:
            main_courses = await self._load_courses(shop.shop_id, CourseType.MAIN)
            if not _matching_courses(main_courses, service_name):
                return _ShopCapability(False)
        if addon_name is not None:
            addon_courses = await self._load_courses(shop.shop_id, CourseType.ADDON)
            if not _matching_courses(addon_courses, addon_name):
                return _ShopCapability(False, main_courses=main_courses)
        if therapist_name is not None or therapist_gender in {"male", "female"}:
            therapists = await self._load_therapists(shop.shop_id)
            if therapist_name is not None and not _matching_therapists_by_name(
                therapists,
                therapist_name,
            ):
                return _ShopCapability(
                    False,
                    main_courses=main_courses,
                    addon_courses=addon_courses,
                )
            if therapist_gender in {"male", "female"} and not _matching_therapists_by_gender(
                therapists,
                therapist_gender,
            ):
                return _ShopCapability(
                    False,
                    main_courses=main_courses,
                    addon_courses=addon_courses,
                )
        return _ShopCapability(
            True,
            main_courses=main_courses,
            addon_courses=addon_courses,
            therapists=therapists,
        )

    # Exact shop match khi đã đủ date/time/people/service/duration và có thể map course an toàn.
    async def _shop_matches_exact_availability(
        self,
        shop: Shop,
        capability: "_ShopCapability",
        criteria: ShopSearchCriteria,
    ) -> bool:
        if (
            criteria.booking_date is None
            or criteria.requested_start_time is None
            or criteria.num_customer is None
            or criteria.duration_minutes is None
            or criteria.requested_main_course_name is None
        ):
            return False

        main_courses = capability.main_courses or await self._load_courses(
            shop.shop_id,
            CourseType.MAIN,
        )
        selected_main = _select_course_for_exact_availability(
            main_courses,
            criteria.requested_main_course_name,
            duration_minutes=criteria.duration_minutes,
        )
        if selected_main is None:
            return False

        addon_ids: tuple[UUID, ...] = ()
        if criteria.requested_addon_name is not None:
            addon_courses = capability.addon_courses or await self._load_courses(
                shop.shop_id,
                CourseType.ADDON,
            )
            selected_addon = _select_course_for_exact_availability(
                addon_courses,
                criteria.requested_addon_name,
                duration_minutes=None,
            )
            if selected_addon is None:
                return False
            addon_ids = (selected_addon.course_id,)

        therapists = capability.therapists
        if (
            (
                criteria.requested_therapist_name is not None
                or criteria.requested_therapist_gender is not None
            )
            and not therapists
        ):
            therapists = await self._load_therapists(shop.shop_id)
        therapist_preference = _availability_therapist_preference(therapists, criteria)
        availability = await self._booking_gateway.get_available_slots(
            AvailabilityRequest(
                shop_id=shop.shop_id,
                booking_date=criteria.booking_date,
                num_customer=criteria.num_customer,
                duration_minutes=criteria.duration_minutes,
                main_course_id=selected_main.course_id,
                addon_ids=addon_ids,
                therapist_preference=therapist_preference,
            )
        )
        return criteria.requested_start_time in availability.slots

    async def _load_courses(
        self,
        shop_id: UUID,
        course_type: CourseType,
    ) -> tuple[Course, ...]:
        return tuple(
            await self._booking_gateway.search_courses(
                CourseSearchRequest(shop_id=shop_id, course_type=course_type, is_active=True)
            )
        )

    async def _load_therapists(self, shop_id: UUID) -> tuple[ShopTherapist, ...]:
        if self._therapist_catalog_gateway is None:
            return ()
        return tuple(
            await self._therapist_catalog_gateway.search_shop_therapists(
                shop_id,
                is_active=True,
            )
        )


@dataclass(frozen=True, slots=True)
class _ShopCapability:
    matches: bool
    main_courses: tuple[Course, ...] = ()
    addon_courses: tuple[Course, ...] = ()
    therapists: tuple[ShopTherapist, ...] = ()


# Chuẩn hóa text tiếng Việt để matching shop không phụ thuộc dấu/case.
def _normalize_search_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.strip().casefold())
    return "".join(
        character for character in decomposed if unicodedata.category(character) != "Mn"
    ).replace("đ", "d")


# Loại shop trùng tên hoặc rỗng để danh sách gợi ý không gây nhiễu cho người dùng.
def _unique_named_shops(shops: list[Shop]) -> list[Shop]:
    """Remove only invalid/duplicate names; never infer activity from wording."""
    if not shops:
        return shops
    unique: list[Shop] = []
    seen: set[str] = set()
    for shop in shops:
        key = _normalize_search_text(shop.name)
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(shop)
    return unique


def _normalized_optional(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = _normalize_search_text(value)
    return normalized or None


def _matching_courses(courses: tuple[Course, ...], query: str) -> tuple[Course, ...]:
    exact = tuple(course for course in courses if _normalize_search_text(course.name) == query)
    if exact:
        return exact
    return tuple(course for course in courses if query in _normalize_search_text(course.name))


def _matching_therapists_by_name(
    therapists: tuple[ShopTherapist, ...],
    query: str,
) -> tuple[ShopTherapist, ...]:
    exact = tuple(item for item in therapists if _normalize_search_text(item.name) == query)
    if exact:
        return exact
    return tuple(item for item in therapists if query in _normalize_search_text(item.name))


def _matching_therapists_by_gender(
    therapists: tuple[ShopTherapist, ...],
    gender: str,
) -> tuple[ShopTherapist, ...]:
    return tuple(item for item in therapists if item.gender.casefold().strip() == gender)


def _select_course_for_exact_availability(
    courses: tuple[Course, ...],
    query: str,
    *,
    duration_minutes: int | None,
) -> Course | None:
    matched = list(_matching_courses(courses, _normalize_search_text(query)))
    if duration_minutes is not None:
        matched = [course for course in matched if course.duration_minutes == duration_minutes]
    if len(matched) == 1:
        return matched[0]
    return None


def _availability_therapist_preference(
    therapists: tuple[ShopTherapist, ...],
    criteria: ShopSearchCriteria,
) -> TherapistPreference | None:
    gender = _normalized_optional(criteria.requested_therapist_gender)
    if gender == "male":
        return TherapistPreference(TherapistPreferenceType.MALE)
    if gender == "female":
        return TherapistPreference(TherapistPreferenceType.FEMALE)
    therapist_name = _normalized_optional(criteria.requested_therapist_name)
    if therapist_name is None:
        return None
    matches = _matching_therapists_by_name(therapists, therapist_name)
    if len(matches) != 1:
        return None
    therapist = matches[0]
    return TherapistPreference(
        TherapistPreferenceType.PERSONAL,
        therapist_id=str(therapist.therapist_id),
        therapist_name=therapist.name,
    )


def _has_exact_availability_shape(criteria: ShopSearchCriteria) -> bool:
    return (
        criteria.booking_date is not None
        and criteria.requested_start_time is not None
        and criteria.num_customer is not None
        and criteria.duration_minutes is not None
        and criteria.requested_main_course_name is not None
    )


def _shop_match_failure_code(criteria: ShopSearchCriteria) -> str:
    if criteria.requested_therapist_name is not None:
        return "therapist_not_supported_in_any_shop"
    if criteria.requested_therapist_gender is not None:
        return "therapist_gender_not_supported_in_any_shop"
    if criteria.requested_addon_name is not None:
        return "addon_not_supported_in_any_shop"
    if criteria.requested_main_course_name is not None:
        if _has_exact_availability_shape(criteria):
            return "requested_shop_time_not_available"
        return "service_not_supported_in_any_shop"
    return "shop_not_found"
