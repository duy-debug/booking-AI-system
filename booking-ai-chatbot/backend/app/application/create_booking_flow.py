from __future__ import annotations

import logging
import re
from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from app.application.contracts import ConversationStore
from app.core.config import settings
from app.core.exceptions import AppError
from app.domain.nlu import NLUResult
from app.domain.state import ConversationState, ConversationStep
from app.tools import read_only
from app.tools.mutation import MutationTools

CREATE_REQUIRED_ENTITIES = (
    "shop_id",
    "main_course_id",
    "addon_course_ids",
    "number_of_people",
    "booking_date",
    "start_time",
)

ALLOWED_SELECTION_ENTITIES = frozenset(
    {
        "shop_id",
        "main_course_id",
        "addon_course_ids",
        "number_of_people",
        "booking_date",
        "start_time",
        "therapist_request_type",
        "therapist_id",
        "therapist_gender",
        "customer",
        "confirmation_token",
    }
)

logger = logging.getLogger(__name__)


class CreateBookingFlow:
    # Nhận dependency qua constructor để workflow không tự khởi tạo Redis hoặc HTTP client.
    def __init__(
        self,
        conversation_store: ConversationStore,
        mutation_tools: MutationTools,
    ) -> None:
        self._store = conversation_store
        self._mutation_tools = mutation_tools

    # Điều phối một lượt của workflow tạo booking và lưu state sau mỗi thay đổi.
    async def handle(
        self,
        conversation_id: str,
        nlu: NLUResult,
        selection: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        state = await self._store.get_state(conversation_id)
        if state.step in {
            ConversationStep.COMPLETED,
            ConversationStep.CANCELLED,
            ConversationStep.FAILED,
        }:
            state = ConversationState(conversation_id=conversation_id)

        state.intent = "create_booking"
        state.merge_entities(self._normalize_nlu_entities(nlu.entities))

        if selection:
            if selection.get("entity") != "confirmation_token":
                await self._store.delete_pending(conversation_id)
            await self._apply_selection(state, selection)

        confirmation_token = state.entities.pop("confirmation_token", None)
        if confirmation_token:
            return await self._confirm_booking(state, str(confirmation_token))

        response = await self._build_next_response(state)
        await self._store.save_state(state)
        return response

    # Đổi tên entity từ NLU sang tên thống nhất mà booking workflow sử dụng.
    @staticmethod
    def _normalize_nlu_entities(entities: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(entities)
        if "phone" in normalized:
            normalized["customer_phone"] = normalized.pop("phone")
        if "booking_date" in normalized:
            normalized["booking_date"] = CreateBookingFlow._validate_booking_date(
                str(normalized["booking_date"])
            )
        if "start_time" in normalized:
            normalized["start_time"] = CreateBookingFlow._validate_start_time(
                str(normalized["start_time"])
            )
        phone = normalized.get("customer_phone")
        if phone and not re.fullmatch(r"0\d{9,10}", str(phone)):
            raise AppError(
                422,
                code="INVALID_CUSTOMER_PHONE",
                detail="Số điện thoại khách hàng không hợp lệ.",
            )
        return normalized

    # Áp dụng lựa chọn có cấu trúc và xác minh lại dữ liệu không đáng tin từ frontend.
    async def _apply_selection(
        self,
        state: ConversationState,
        selection: dict[str, Any],
    ) -> None:
        entity = str(selection.get("entity", ""))
        value = selection.get("value")
        if entity not in ALLOWED_SELECTION_ENTITIES:
            raise AppError(
                422,
                code="UNSUPPORTED_SELECTION_ENTITY",
                detail="Loại lựa chọn không được hỗ trợ trong luồng tạo booking.",
            )

        if entity == "shop_id":
            shop = await read_only.get_shop(str(value))
            state.entities["shop_id"] = str(shop["shop_id"])
            state.entities["shop_name"] = str(shop["name"])
            self._clear_after_shop(state)
            return

        if entity == "main_course_id":
            course = await self._validate_main_course(state, str(value))
            state.entities["main_course_id"] = str(course["course_id"])
            state.entities["main_course_name"] = str(course["name"])
            state.entities["course_duration_minutes"] = int(course["duration_minutes"])
            state.entities["course_price"] = str(course["price"])
            self._clear_after_course(state)
            return

        if entity == "addon_course_ids":
            addons = await self._validate_addon_courses(state, value)
            state.entities["addon_course_ids"] = [str(course["course_id"]) for course in addons]
            state.entities["addon_course_names"] = [str(course["name"]) for course in addons]
            state.entities.pop("start_time", None)
            return

        if entity == "number_of_people":
            people = int(value)
            if people not in {1, 2, 3}:
                raise AppError(
                    422,
                    code="INVALID_NUMBER_OF_PEOPLE",
                    detail="Số người chỉ được phép là 1, 2 hoặc 3.",
                )
            state.entities["number_of_people"] = people
            state.entities.pop("start_time", None)
            self._reset_therapist_request(state)
            if people > 1:
                state.entities["therapist_request_type"] = "none"
            return

        if entity == "booking_date":
            state.entities["booking_date"] = self._validate_booking_date(str(value))
            state.entities.pop("start_time", None)
            return

        if entity == "start_time":
            state.entities["start_time"] = self._validate_start_time(str(value))
            self._reset_therapist_request(state)
            if int(state.entities.get("number_of_people", 1)) > 1:
                state.entities["therapist_request_type"] = "none"
            return

        if entity == "therapist_request_type":
            self._apply_therapist_request_type(state, str(value))
            return

        if entity == "therapist_id":
            therapist = await self._validate_specific_therapist(state, str(value))
            state.entities["therapist_id"] = str(therapist["therapist_id"])
            state.entities["therapist_name"] = str(therapist["name"])
            return

        if entity == "therapist_gender":
            gender = str(value)
            if gender not in {"male", "female"}:
                raise AppError(
                    422,
                    code="INVALID_THERAPIST_GENDER",
                    detail="Giới tính therapist phải là male hoặc female.",
                )
            state.entities["therapist_gender"] = gender
            return

        if entity == "customer":
            self._apply_customer(state, value)
            return

        state.entities["confirmation_token"] = str(value).upper()

    # Xác minh course chính thuộc đúng shop hiện tại và đang được public API trả về.
    @staticmethod
    async def _validate_main_course(
        state: ConversationState,
        course_id: str,
    ) -> dict[str, Any]:
        shop_id = state.entities.get("shop_id")
        if not shop_id:
            raise AppError(
                409,
                code="SHOP_REQUIRED_BEFORE_COURSE",
                detail="Cần chọn cửa hàng trước khi chọn dịch vụ.",
            )
        courses = await read_only.list_courses(str(shop_id), course_type="main")
        course = next(
            (
                item
                for item in courses
                if str(item.get("course_id")) == course_id and item.get("course_type") == "main"
            ),
            None,
        )
        if course is None:
            raise AppError(
                422,
                code="INVALID_MAIN_COURSE",
                detail="Dịch vụ chính không thuộc cửa hàng đã chọn.",
            )
        return course

    # Xác minh toàn bộ add-on thuộc đúng shop và không chấp nhận ID lạ từ frontend.
    @staticmethod
    async def _validate_addon_courses(
        state: ConversationState,
        value: Any,
    ) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            raise AppError(
                422,
                code="INVALID_ADDON_COURSES",
                detail="Danh sách add-on phải là một mảng ID.",
            )
        requested_ids = [str(course_id) for course_id in value]
        if len(requested_ids) != len(set(requested_ids)):
            raise AppError(
                422,
                code="DUPLICATE_ADDON_COURSE",
                detail="Danh sách add-on không được chứa ID trùng nhau.",
            )
        if not requested_ids:
            return []

        courses = await read_only.list_courses(
            str(state.entities["shop_id"]),
            course_type="addon",
        )
        by_id = {
            str(course["course_id"]): course
            for course in courses
            if course.get("course_type") == "addon"
        }
        if any(course_id not in by_id for course_id in requested_ids):
            raise AppError(
                422,
                code="INVALID_ADDON_COURSE",
                detail="Có add-on không thuộc cửa hàng đã chọn.",
            )
        return [by_id[course_id] for course_id in requested_ids]

    # Chuẩn hóa form khách hàng và chỉ giữ những field Backend cần.
    @staticmethod
    def _apply_customer(state: ConversationState, value: Any) -> None:
        if not isinstance(value, dict):
            raise AppError(
                422,
                code="INVALID_CUSTOMER_DATA",
                detail="Thông tin khách hàng phải là một object.",
            )
        phone = str(value.get("phone", "")).strip()
        if not re.fullmatch(r"0\d{9,10}", phone):
            raise AppError(
                422,
                code="INVALID_CUSTOMER_PHONE",
                detail="Số điện thoại khách hàng không hợp lệ.",
            )
        state.entities["customer_phone"] = phone
        name = str(value.get("name", "")).strip()
        if name:
            state.entities["customer_name"] = name[:100]

    # Áp dụng loại yêu cầu therapist và cấm chỉ định cho booking nhóm.
    @staticmethod
    def _apply_therapist_request_type(
        state: ConversationState,
        request_type: str,
    ) -> None:
        if request_type not in {"none", "specific", "gender"}:
            raise AppError(
                422,
                code="INVALID_THERAPIST_REQUEST_TYPE",
                detail="Loại yêu cầu therapist không hợp lệ.",
            )
        people = int(state.entities.get("number_of_people", 1))
        if people > 1 and request_type != "none":
            raise AppError(
                422,
                code="GROUP_BOOKING_THERAPIST_MUST_BE_AUTO",
                detail="Booking nhóm không được chỉ định therapist.",
            )
        state.entities["therapist_request_type"] = request_type
        state.entities.pop("therapist_id", None)
        state.entities.pop("therapist_name", None)
        state.entities.pop("therapist_gender", None)

    # Xác minh therapist cụ thể còn trống trong đúng slot đã chọn.
    async def _validate_specific_therapist(
        self,
        state: ConversationState,
        therapist_id: str,
    ) -> dict[str, Any]:
        if state.entities.get("therapist_request_type") != "specific":
            raise AppError(
                409,
                code="SPECIFIC_THERAPIST_NOT_REQUESTED",
                detail="Cần chọn loại yêu cầu therapist cụ thể trước.",
            )
        slot = await self._get_selected_available_slot(state)
        therapists = await read_only.get_available_therapists(
            shop_id=str(state.entities["shop_id"]),
            booking_date=str(state.entities["booking_date"]),
            start_time=str(state.entities["start_time"]),
            end_time=self._normalize_api_time(slot["end_time"]),
        )
        therapist = next(
            (
                item
                for item in therapists
                if str(item.get("therapist_id")) == therapist_id
                and bool(item.get("available", True))
            ),
            None,
        )
        if therapist is None:
            raise AppError(
                409,
                code="THERAPIST_NOT_AVAILABLE",
                detail="Therapist đã chọn không còn khả dụng trong khung giờ này.",
            )
        return therapist

    # Kiểm tra ngày ISO và không cho phép chọn ngày trong quá khứ.
    @staticmethod
    def _validate_booking_date(value: str) -> str:
        try:
            booking_date = date.fromisoformat(value)
        except ValueError as exc:
            raise AppError(
                422,
                code="INVALID_BOOKING_DATE",
                detail="Ngày booking phải theo định dạng YYYY-MM-DD.",
            ) from exc
        if booking_date < CreateBookingFlow._business_today():
            raise AppError(
                422,
                code="BOOKING_DATE_IN_PAST",
                detail="Không thể đặt booking trong quá khứ.",
            )
        return booking_date.isoformat()

    # Lấy ngày hiện tại theo múi giờ nghiệp vụ thay vì phụ thuộc timezone của máy chạy.
    @staticmethod
    def _business_today() -> date:
        return datetime.now(ZoneInfo(settings.BUSINESS_TIMEZONE)).date()

    # Kiểm tra giờ theo định dạng 24 giờ và chuẩn hóa thành HH:MM.
    @staticmethod
    def _validate_start_time(value: str) -> str:
        try:
            start = time.fromisoformat(value)
        except ValueError as exc:
            raise AppError(
                422,
                code="INVALID_START_TIME",
                detail="Giờ bắt đầu phải theo định dạng HH:MM.",
            ) from exc
        return start.strftime("%H:%M")

    # Xóa các lựa chọn phụ thuộc khi khách hàng đổi shop.
    @staticmethod
    def _clear_after_shop(state: ConversationState) -> None:
        for key in (
            "main_course_id",
            "main_course_name",
            "course_duration_minutes",
            "course_price",
            "addon_course_ids",
            "addon_course_names",
            "start_time",
            "therapist_request_type",
            "therapist_id",
            "therapist_name",
            "therapist_gender",
        ):
            state.entities.pop(key, None)

    # Xóa giờ đã chọn vì đổi course sẽ làm thay đổi thời lượng và availability.
    @staticmethod
    def _clear_after_course(state: ConversationState) -> None:
        state.entities.pop("addon_course_ids", None)
        state.entities.pop("addon_course_names", None)
        state.entities.pop("start_time", None)
        CreateBookingFlow._reset_therapist_request(state)

    # Xóa yêu cầu therapist phụ thuộc vào số người hoặc slot cũ.
    @staticmethod
    def _reset_therapist_request(state: ConversationState) -> None:
        for key in (
            "therapist_request_type",
            "therapist_id",
            "therapist_name",
            "therapist_gender",
        ):
            state.entities.pop(key, None)

    # Chọn response kế tiếp theo entity đầu tiên còn thiếu trong state.
    async def _build_next_response(
        self,
        state: ConversationState,
    ) -> dict[str, Any]:
        missing = self._missing_entities(state)
        if not missing:
            return await self._prepare_confirmation(state)

        entity = missing[0]
        if entity == "shop_id":
            return await self._shop_response(state, missing)
        if entity == "main_course_id":
            return await self._course_response(state, missing)
        if entity == "addon_course_ids":
            return await self._addon_response(state, missing)
        if entity == "number_of_people":
            return self._people_response(state, missing)
        if entity == "booking_date":
            return self._date_response(state, missing)
        if entity == "start_time":
            return await self._slot_response(state, missing)
        if entity == "therapist_request_type":
            return self._therapist_request_response(state, missing)
        if entity == "therapist_id":
            return await self._specific_therapist_response(state, missing)
        if entity == "therapist_gender":
            return self._therapist_gender_response(state, missing)
        return self._customer_response(state, missing)

    # Trả danh sách entity còn thiếu theo đúng thứ tự workflow.
    @staticmethod
    def _missing_entities(state: ConversationState) -> list[str]:
        missing: list[str] = []
        for entity in CREATE_REQUIRED_ENTITIES:
            if entity == "addon_course_ids":
                if entity not in state.entities:
                    missing.append(entity)
                continue
            if state.entities.get(entity) in {None, ""}:
                missing.append(entity)
        if state.entities.get("start_time"):
            request_type = state.entities.get("therapist_request_type")
            if request_type is None:
                missing.append("therapist_request_type")
            elif request_type == "specific" and not state.entities.get("therapist_id"):
                missing.append("therapist_id")
            elif request_type == "gender" and not state.entities.get("therapist_gender"):
                missing.append("therapist_gender")
        if not state.entities.get("customer_phone"):
            missing.append("customer_phone")
        return missing

    # Lấy shop thật từ Booking Backend và tạo UI options.
    @staticmethod
    async def _shop_response(
        state: ConversationState,
        missing: list[str],
    ) -> dict[str, Any]:
        state.step = ConversationStep.COLLECT_SHOP
        shops = await read_only.list_shops()
        return {
            "answer": "Bạn muốn đặt tại cửa hàng nào?",
            "missing_entities": missing,
            "ui": {
                "type": "shop_options",
                "options": [
                    {
                        "id": str(shop["shop_id"]),
                        "label": str(shop["name"]),
                        "description": shop.get("address"),
                        "metadata": {},
                    }
                    for shop in shops
                ],
                "data": {},
            },
        }

    # Trả danh sách add-on và cho phép gửi mảng rỗng để xác nhận bỏ qua.
    @staticmethod
    async def _addon_response(
        state: ConversationState,
        missing: list[str],
    ) -> dict[str, Any]:
        state.step = ConversationStep.COLLECT_ADDONS
        addons = await read_only.list_courses(
            str(state.entities["shop_id"]),
            course_type="addon",
        )
        return {
            "answer": "Bạn có muốn chọn thêm dịch vụ add-on không?",
            "missing_entities": missing,
            "ui": {
                "type": "addon_options",
                "options": [
                    {
                        "id": str(course["course_id"]),
                        "label": str(course["name"]),
                        "description": (f"{course['duration_minutes']} phút · {course['price']}"),
                        "metadata": {
                            "duration_minutes": course["duration_minutes"],
                            "price": str(course["price"]),
                        },
                    }
                    for course in addons
                ],
                "data": {
                    "multiple": True,
                    "allow_skip": True,
                    "selection_entity": "addon_course_ids",
                },
            },
        }

    # Lấy course chính thuộc shop đã chọn và tạo UI options.
    @staticmethod
    async def _course_response(
        state: ConversationState,
        missing: list[str],
    ) -> dict[str, Any]:
        state.step = ConversationStep.COLLECT_SERVICE
        courses = await read_only.list_courses(
            str(state.entities["shop_id"]),
            course_type="main",
        )
        return {
            "answer": "Bạn muốn chọn dịch vụ nào?",
            "missing_entities": missing,
            "ui": {
                "type": "course_options",
                "options": [
                    {
                        "id": str(course["course_id"]),
                        "label": str(course["name"]),
                        "description": (f"{course['duration_minutes']} phút · {course['price']}"),
                        "metadata": {
                            "duration_minutes": course["duration_minutes"],
                            "price": str(course["price"]),
                        },
                    }
                    for course in courses
                ],
                "data": {},
            },
        }

    # Yêu cầu số người trước khi tra availability vì mỗi người cần một therapist.
    @staticmethod
    def _people_response(
        state: ConversationState,
        missing: list[str],
    ) -> dict[str, Any]:
        state.step = ConversationStep.COLLECT_PEOPLE
        return {
            "answer": "Booking này dành cho bao nhiêu người?",
            "missing_entities": missing,
            "ui": {
                "type": "people_options",
                "options": [
                    {"id": str(value), "label": f"{value} người", "metadata": {}}
                    for value in (1, 2, 3)
                ],
                "data": {},
            },
        }

    # Trả date picker; giới hạn cụ thể vẫn được Booking Backend xác minh lại.
    @staticmethod
    def _date_response(
        state: ConversationState,
        missing: list[str],
    ) -> dict[str, Any]:
        state.step = ConversationStep.COLLECT_DATE
        return {
            "answer": "Bạn muốn đặt vào ngày nào?",
            "missing_entities": missing,
            "ui": {
                "type": "date_picker",
                "options": [],
                "data": {"min_date": CreateBookingFlow._business_today().isoformat()},
            },
        }

    # Tra slot theo shop, course, ngày và số người đã chọn.
    @staticmethod
    async def _slot_response(
        state: ConversationState,
        missing: list[str],
    ) -> dict[str, Any]:
        state.step = ConversationStep.COLLECT_TIME
        availability = await read_only.get_available_slots(
            shop_id=str(state.entities["shop_id"]),
            booking_date=str(state.entities["booking_date"]),
            number_of_people=int(state.entities["number_of_people"]),
            main_course_id=str(state.entities["main_course_id"]),
            addon_course_ids=CreateBookingFlow._addon_query_value(state),
            therapist_request_type="none",
        )
        slots = [slot for slot in availability.get("data", []) if bool(slot.get("available"))]
        return {
            "answer": (
                "Vui lòng chọn khung giờ còn trống."
                if slots
                else "Ngày đã chọn không còn khung giờ phù hợp."
            ),
            "missing_entities": missing,
            "ui": {
                "type": "slot_options",
                "options": [
                    {
                        "id": CreateBookingFlow._normalize_api_time(slot["start_time"]),
                        "label": (
                            f"{CreateBookingFlow._normalize_api_time(slot['start_time'])} - "
                            f"{CreateBookingFlow._normalize_api_time(slot['end_time'])}"
                        ),
                        "description": None,
                        "metadata": {
                            "end_time": slot["end_time"],
                            "duration_minutes": slot["duration_minutes"],
                        },
                    }
                    for slot in slots
                ],
                "data": {"booking_date": state.entities["booking_date"]},
            },
        }

    # Yêu cầu form khách hàng sau khi đã chọn đủ thông tin dịch vụ và thời gian.
    @staticmethod
    def _customer_response(
        state: ConversationState,
        missing: list[str],
    ) -> dict[str, Any]:
        state.step = ConversationStep.COLLECT_CUSTOMER
        return {
            "answer": "Vui lòng nhập tên và số điện thoại khách hàng.",
            "missing_entities": missing,
            "ui": {
                "type": "customer_form",
                "options": [],
                "data": {
                    "fields": [
                        {"name": "name", "required": False},
                        {"name": "phone", "required": True},
                    ]
                },
            },
        }

    # Hỏi preference therapist chỉ với booking một người; booking nhóm đã ép auto.
    @staticmethod
    def _therapist_request_response(
        state: ConversationState,
        missing: list[str],
    ) -> dict[str, Any]:
        state.step = ConversationStep.COLLECT_THERAPIST_REQUEST
        return {
            "answer": "Bạn có yêu cầu therapist cụ thể không?",
            "missing_entities": missing,
            "ui": {
                "type": "therapist_request_options",
                "options": [
                    {"id": "none", "label": "Tự động phân công", "metadata": {}},
                    {
                        "id": "specific",
                        "label": "Chọn therapist cụ thể",
                        "metadata": {},
                    },
                    {
                        "id": "gender",
                        "label": "Chọn theo giới tính",
                        "metadata": {},
                    },
                ],
                "data": {},
            },
        }

    # Trả danh sách therapist còn trống trong slot cho booking một người.
    async def _specific_therapist_response(
        self,
        state: ConversationState,
        missing: list[str],
    ) -> dict[str, Any]:
        state.step = ConversationStep.COLLECT_THERAPIST_REQUEST
        slot = await self._get_selected_available_slot(state)
        therapists = await read_only.get_available_therapists(
            shop_id=str(state.entities["shop_id"]),
            booking_date=str(state.entities["booking_date"]),
            start_time=str(state.entities["start_time"]),
            end_time=self._normalize_api_time(slot["end_time"]),
        )
        return {
            "answer": "Vui lòng chọn therapist còn trống.",
            "missing_entities": missing,
            "ui": {
                "type": "therapist_options",
                "options": [
                    {
                        "id": str(therapist["therapist_id"]),
                        "label": str(therapist["name"]),
                        "description": therapist.get("gender"),
                        "metadata": {},
                    }
                    for therapist in therapists
                    if bool(therapist.get("available", True))
                ],
                "data": {},
            },
        }

    # Trả hai lựa chọn giới tính được Public Booking API hỗ trợ.
    @staticmethod
    def _therapist_gender_response(
        state: ConversationState,
        missing: list[str],
    ) -> dict[str, Any]:
        state.step = ConversationStep.COLLECT_THERAPIST_REQUEST
        return {
            "answer": "Bạn muốn therapist nam hay nữ?",
            "missing_entities": missing,
            "ui": {
                "type": "gender_options",
                "options": [
                    {"id": "male", "label": "Nam", "metadata": {}},
                    {"id": "female", "label": "Nữ", "metadata": {}},
                ],
                "data": {},
            },
        }

    # Kiểm tra eligibility và slot lần cuối trước khi đóng băng payload xác nhận.
    async def _prepare_confirmation(
        self,
        state: ConversationState,
    ) -> dict[str, Any]:
        state.step = ConversationStep.CHECK_AVAILABILITY
        eligibility = await read_only.check_eligibility(
            phone=str(state.entities["customer_phone"]),
            shop_id=str(state.entities["shop_id"]),
        )
        if not bool(eligibility.get("eligible")):
            raise AppError(
                403,
                code="CUSTOMER_NOT_ELIGIBLE",
                detail="Khách hàng không đủ điều kiện tạo booking.",
            )
        selected_slot = await self._get_selected_available_slot(state)
        pending = await self._store.get_pending(state.conversation_id)
        if pending is None or pending.action != "create_booking":
            pending = await self._mutation_tools.prepare(
                state.conversation_id,
                "create_booking",
                self._build_booking_payload(state),
            )
        state.step = ConversationStep.AWAIT_CONFIRMATION
        summary = self._build_summary(state, selected_slot)
        return {
            "answer": "Vui lòng kiểm tra thông tin và xác nhận tạo booking.",
            "missing_entities": [],
            "data": summary,
            "ui": {
                "type": "booking_summary",
                "options": [
                    {
                        "id": pending.confirmation_token,
                        "label": "Xác nhận đặt lịch",
                        "metadata": {},
                    }
                ],
                "data": {
                    **summary,
                    "confirmation_token": pending.confirmation_token,
                    "expires_at": pending.expires_at.isoformat(),
                },
            },
        }

    # Kiểm tra lại slot cùng therapist request hiện tại và trả slot đã xác minh.
    async def _get_selected_available_slot(
        self,
        state: ConversationState,
    ) -> dict[str, Any]:
        request_type = str(state.entities.get("therapist_request_type", "none"))
        availability = await read_only.get_available_slots(
            shop_id=str(state.entities["shop_id"]),
            booking_date=str(state.entities["booking_date"]),
            start_time=str(state.entities["start_time"]),
            number_of_people=int(state.entities["number_of_people"]),
            main_course_id=str(state.entities["main_course_id"]),
            addon_course_ids=self._addon_query_value(state),
            therapist_request_type=request_type,
            therapist_id=state.entities.get("therapist_id"),
            therapist_gender=state.entities.get("therapist_gender"),
        )
        selected_slot = next(
            (
                slot
                for slot in availability.get("data", [])
                if self._normalize_api_time(slot.get("start_time")) == state.entities["start_time"]
                and bool(slot.get("available"))
            ),
            None,
        )
        if selected_slot is None:
            state.entities.pop("start_time", None)
            state.step = ConversationStep.COLLECT_TIME
            await self._store.save_state(state)
            raise AppError(
                409,
                code="SELECTED_SLOT_UNAVAILABLE",
                detail="Khung giờ đã chọn không còn khả dụng. Vui lòng chọn lại.",
            )
        return selected_slot

    # Tạo payload đúng schema Public Booking API và không truyền field UI nội bộ.
    @staticmethod
    def _build_booking_payload(state: ConversationState) -> dict[str, Any]:
        people = int(state.entities["number_of_people"])
        return {
            "shop_id": state.entities["shop_id"],
            "booking_date": state.entities["booking_date"],
            "start_time": state.entities["start_time"],
            "number_of_people": people,
            "customer": {
                "phone": state.entities["customer_phone"],
                "name": state.entities.get("customer_name"),
            },
            "courses": [
                {
                    "course_id": state.entities["main_course_id"],
                    "course_role": "main",
                },
                *[
                    {"course_id": course_id, "course_role": "addon"}
                    for course_id in state.entities.get("addon_course_ids", [])
                ],
            ],
            "therapist_request": CreateBookingFlow._build_therapist_request(state),
            "confirmed_by_customer": True,
        }

    # Tạo summary chỉ từ dữ liệu đã được Booking Backend xác minh.
    @staticmethod
    def _build_summary(
        state: ConversationState,
        selected_slot: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "shop_id": state.entities["shop_id"],
            "shop_name": state.entities.get("shop_name"),
            "main_course_id": state.entities["main_course_id"],
            "main_course_name": state.entities.get("main_course_name"),
            "addon_course_ids": state.entities.get("addon_course_ids", []),
            "addon_course_names": state.entities.get("addon_course_names", []),
            "booking_date": state.entities["booking_date"],
            "start_time": CreateBookingFlow._normalize_api_time(selected_slot["start_time"]),
            "end_time": CreateBookingFlow._normalize_api_time(selected_slot["end_time"]),
            "number_of_people": state.entities["number_of_people"],
            "customer_name": state.entities.get("customer_name"),
            "customer_phone": state.entities["customer_phone"],
            "price_per_person": state.entities.get("course_price"),
            "therapist_request_type": state.entities.get("therapist_request_type", "none"),
            "therapist_id": state.entities.get("therapist_id"),
            "therapist_name": state.entities.get("therapist_name"),
            "therapist_gender": state.entities.get("therapist_gender"),
        }

    # Tạo therapist request đúng schema và luôn trả none đối với booking nhóm.
    @staticmethod
    def _build_therapist_request(state: ConversationState) -> dict[str, Any]:
        if int(state.entities["number_of_people"]) > 1:
            return {"type": "none"}
        request_type = str(state.entities.get("therapist_request_type", "none"))
        if request_type == "specific":
            return {
                "type": "specific",
                "therapist_id": state.entities["therapist_id"],
            }
        if request_type == "gender":
            return {
                "type": "gender",
                "gender": state.entities["therapist_gender"],
            }
        return {"type": "none"}

    # Chuyển danh sách add-on sang query CSV mà Public Availability API yêu cầu.
    @staticmethod
    def _addon_query_value(state: ConversationState) -> str | None:
        addon_ids = state.entities.get("addon_course_ids", [])
        return ",".join(str(course_id) for course_id in addon_ids) or None

    # Chuẩn hóa kiểu time JSON của Backend từ HH:MM:SS về định dạng UI HH:MM.
    @staticmethod
    def _normalize_api_time(value: Any) -> str:
        return str(value)[:5]

    # Thực thi mutation đã xác nhận và chuyển state sang trạng thái hoàn tất.
    async def _confirm_booking(
        self,
        state: ConversationState,
        confirmation_token: str,
    ) -> dict[str, Any]:
        if state.step is not ConversationStep.AWAIT_CONFIRMATION:
            raise AppError(
                409,
                code="BOOKING_NOT_AWAITING_CONFIRMATION",
                detail="Booking chưa sẵn sàng để xác nhận.",
            )
        result = await self._mutation_tools.confirm(
            state.conversation_id,
            confirmation_token,
        )
        state.step = ConversationStep.COMPLETED
        state.entities = {"booking_id": result.get("booking_id")}
        try:
            await self._store.save_state(state)
        except AppError as exc:
            if exc.code != "CONVERSATION_STATE_CONFLICT":
                raise
            logger.warning(
                "Booking đã tạo nhưng conversation state bị conflict",
                extra={"conversation_id": state.conversation_id},
            )
        return {
            "answer": "Đặt lịch thành công.",
            "missing_entities": [],
            "data": result,
            "ui": {
                "type": "booking_result",
                "options": [],
                "data": result,
            },
        }
