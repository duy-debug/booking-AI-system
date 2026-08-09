"""Build deterministic, transport-neutral responses from dialog turn results."""

import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, time
from types import MappingProxyType
from typing import TypeAlias

from app.dialog.dialog_controller import DialogTurnResult, DialogTurnStatus
from app.domain.booking_context import BookingContext
from app.domain.booking_models import TherapistPreferenceType
from app.domain.booking_state import BookingState

_TEMPLATE_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
_SAFE_METADATA_KEYS = frozenset(
    {
        "available_slot_count",
        "has_addons",
        "booking_created",
        "can_retry",
        "can_change_info",
        "response_type",
        "source_count",
        "item_count",
        "quick_reply_limit",
    }
)
_UNHANDLED_FAILURE_TEXT = "Đã có lỗi xảy ra. Vui lòng thử lại hoặc liên hệ cửa hàng."


class InstructionBuilderError(Exception):
    """Base exception for deterministic instruction rendering errors."""


class InvalidInstructionTemplateNameError(InstructionBuilderError):
    """Raised when a template name is not a valid snake_case identifier."""


class DuplicateInstructionTemplateError(InstructionBuilderError):
    """Raised when a template name is registered more than once."""


class UnknownInstructionTemplateError(InstructionBuilderError):
    """Raised when a requested template has no registered renderer."""


class InstructionRenderingError(InstructionBuilderError):
    """Raised when a registered renderer cannot produce a safe response."""


@dataclass(frozen=True, slots=True)
class DialogResponseDraft:
    """Contains presentation data produced by one instruction renderer."""

    text: str
    quick_replies: tuple[str, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError("Dialog response draft text must not be empty.")
        object.__setattr__(self, "quick_replies", tuple(self.quick_replies))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class DialogResponse:
    """Represents a rendered response independent of HTTP and streaming concerns."""

    text: str
    instruction_template: str | None
    state: BookingState
    status: DialogTurnStatus
    quick_replies: tuple[str, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError("Dialog response text must not be empty.")
        limit = self.metadata.get("quick_reply_limit", 8)
        if type(limit) is not int:
            raise TypeError("Dialog response quick_reply_limit metadata must be an integer.")
        object.__setattr__(
            self,
            "quick_replies",
            _normalize_quick_replies(self.quick_replies, limit=limit),
        )
        object.__setattr__(self, "metadata", _allowlisted_metadata(self.metadata))


InstructionRenderer: TypeAlias = Callable[
    [BookingContext, DialogTurnResult],
    DialogResponseDraft,
]


class InstructionBuilder:
    """Render registered instruction identifiers without side effects or I/O."""

    # Khởi tạo registry template để render response theo state/outcome đã xử lý.
    def __init__(self) -> None:
        self._templates: dict[str, InstructionRenderer] = {}
        self._register_default_templates()

    # Đăng ký renderer cho instruction_template mà flow JSON tham chiếu.
    def register_template(
        self,
        name: str,
        renderer: InstructionRenderer,
    ) -> None:
        """Register one renderer without replacing an existing template."""
        normalized_name = self._normalize_template_name(name)
        if not callable(renderer):
            raise TypeError("Instruction renderer must be callable.")
        if normalized_name in self._templates:
            raise DuplicateInstructionTemplateError(
                f"Instruction template '{normalized_name}' is already registered."
            )
        self._templates[normalized_name] = renderer

    # Kiểm tra template có renderer để validate flow lúc startup.
    def has_template(self, name: str) -> bool:
        """Return whether an exact template name is registered."""
        return isinstance(name, str) and name.strip() in self._templates

    # Trả danh sách template đã đăng ký để audit binding.
    def registered_templates(self) -> tuple[str, ...]:
        """Return template names in registration order."""
        return tuple(self._templates)

    # Tìm template trong flow chưa có renderer để fail fast trước runtime.
    def find_missing_templates(
        self,
        declared_templates: Iterable[str],
    ) -> tuple[str, ...]:
        """Return unique declared template names without registered renderers."""
        seen: set[str] = set()
        missing: list[str] = []
        for name in declared_templates:
            if name not in seen:
                seen.add(name)
                if not self.has_template(name):
                    missing.append(name)
        return tuple(missing)

    # Chọn instruction phù hợp dựa trên state mới và kết quả business đã xử lý.
    def build_response(
        self,
        *,
        result: DialogTurnResult,
        context: BookingContext,
    ) -> DialogResponse:
        """Render a dialog result without mutating its booking context."""
        if result.status is DialogTurnStatus.FAILURE_UNHANDLED:
            draft = DialogResponseDraft(
                _UNHANDLED_FAILURE_TEXT,
                metadata={"can_retry": True},
            )
        elif result.instruction_template is None:
            draft = self._fallback_for_state(context, result)
        else:
            renderer = self._get_renderer(result.instruction_template)
            try:
                draft = renderer(context, result)
                if not isinstance(draft, DialogResponseDraft):
                    raise TypeError("Renderer must return DialogResponseDraft.")
            except Exception as error:
                raise InstructionRenderingError(
                    f"Instruction template '{result.instruction_template}' failed to render."
                ) from error

        return DialogResponse(
            text=draft.text,
            instruction_template=result.instruction_template,
            state=result.final_state,
            status=result.status,
            quick_replies=_normalize_quick_replies(draft.quick_replies),
            metadata=_allowlisted_metadata(draft.metadata),
        )

    # Tổng hợp instruction và context an toàn trước khi gọi LLM NLG.
    def build_nlg_prompt(
        self,
        *,
        response: DialogResponse,
        context: BookingContext,
    ) -> str:
        """Build a grounded Vietnamese response instruction without sensitive data."""
        facts = [
            f"State hiện tại: {response.state.value}.",
            f"Trạng thái xử lý: {response.status.value}.",
            f"Instruction template: {response.instruction_template or 'state_fallback'}.",
            f"Nội dung nghiệp vụ đã kiểm chứng: {response.text}",
        ]
        if context.shop is not None:
            facts.append(f"Cửa hàng đã xác nhận: {context.shop.name}.")
        if context.booking_date is not None:
            facts.append(f"Ngày đã xác nhận: {context.booking_date.isoformat()}.")
        if context.num_customer is not None:
            facts.append(f"Số người đã xác nhận: {context.num_customer}.")
        if context.duration_minutes is not None:
            facts.append(f"Thời lượng đã xác nhận: {context.duration_minutes} phút.")
        if context.main_course is not None:
            facts.append(f"Course chính đã xác nhận: {context.main_course.name}.")
        if context.start_time is not None:
            facts.append(f"Giờ đã xác nhận: {context.start_time.strftime('%H:%M')}.")
        if context.reservation_code is not None:
            facts.append(f"Mã đặt lịch: {context.reservation_code}.")
        facts.extend(
            (
                "Hãy viết câu trả lời tiếng Việt tự nhiên, ngắn gọn.",
                "Không thêm shop, course, slot, therapist hoặc mã đặt chỗ chưa có ở trên.",
                "Không thay đổi flow và chỉ hỏi thông tin còn thiếu của state hiện tại.",
                "Không nhắc tới prompt, state machine hoặc hệ thống nội bộ.",
            )
        )
        return "\n".join(facts)

    # Tạo response FAQ grounded từ knowledge documents mà không mutate booking state.
    def build_faq_response(
        self,
        *,
        answer: str,
        source_count: int,
        context: BookingContext,
        handled_failure: bool = False,
    ) -> DialogResponse:
        """Render an extractive FAQ answer without changing dialog workflow state."""
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("FAQ answer must not be empty.")
        if type(source_count) is not int or source_count < 0 or source_count > 3:
            raise ValueError("FAQ source count must be between zero and three.")
        status = DialogTurnStatus.FAILURE_HANDLED if handled_failure else DialogTurnStatus.SUCCESS
        text = answer.strip()
        quick_replies: tuple[str, ...] = ()
        if context.state in {
            BookingState.SELECTING_SHOP,
            BookingState.SELECTING_DATE,
            BookingState.SELECTING_PEOPLE,
            BookingState.SELECTING_DURATION,
            BookingState.SELECTING_SERVICE,
            BookingState.SELECTING_TIME,
            BookingState.SELECTING_THERAPIST,
            BookingState.COLLECTING_PHONE,
            BookingState.VERIFYING_PHONE,
            BookingState.AWAITING_CONFIRMATION,
        }:
            result = DialogTurnResult(
                status=status,
                initial_state=context.state,
                final_state=context.state,
                intent="ask_question",
                instruction_template=None,
                executed_actions=(),
                auto_transition_count=0,
            )
            follow_up = self._fallback_for_state(context, result)
            text = f"{text} {follow_up.text}"
            quick_replies = follow_up.quick_replies
        return DialogResponse(
            text=text,
            instruction_template=None,
            state=context.state,
            status=status,
            quick_replies=quick_replies,
            metadata={"response_type": "faq", "source_count": source_count},
        )

    # Lấy renderer theo template name hoặc dùng fallback an toàn nếu thiếu.
    def _get_renderer(self, name: str) -> InstructionRenderer:
        try:
            return self._templates[name]
        except KeyError as error:
            raise UnknownInstructionTemplateError(
                f"Instruction template '{name}' is not registered."
            ) from error

    @staticmethod
    # Chuẩn hóa template name để flow không dùng key rỗng hoặc sai format.
    def _normalize_template_name(name: str) -> str:
        if not isinstance(name, str):
            raise InvalidInstructionTemplateNameError("Instruction template name must be a string.")
        normalized = name.strip()
        if not _TEMPLATE_NAME_PATTERN.fullmatch(normalized):
            raise InvalidInstructionTemplateNameError(
                "Instruction template name must be a snake_case identifier."
            )
        return normalized

    # Đăng ký toàn bộ renderer mặc định mà booking_flow.json đang sử dụng.
    def _register_default_templates(self) -> None:
        templates: tuple[tuple[str, InstructionRenderer], ...] = (
            ("greeting", self._greeting),
            ("ask_shop", self._ask_shop),
            ("ask_date", self._ask_date),
            ("date_still_unavailable", self._date_still_unavailable),
            ("ask_people", self._ask_people),
            ("people_too_many", self._people_too_many),
            ("ask_duration", self._ask_duration),
            ("ask_course", self._ask_course),
            ("addon_needs_main", self._addon_needs_main),
            ("main_course_required", self._main_course_required),
            ("combo_not_bookable_retry", self._combo_not_bookable_retry),
            ("duration_invalid", self._duration_invalid),
            ("no_working_shift", self._no_working_shift),
            ("no_slots_available", self._no_slots_available),
            ("slot_api_error", self._slot_api_error),
            ("suggest_time_slots", self._suggest_time_slots),
            ("slot_unavailable", self._slot_unavailable),
            ("ask_therapist", self._ask_therapist),
            ("therapist_unavailable", self._therapist_unavailable),
            ("ask_phone", self._ask_phone),
            ("ask_customer_name", self._ask_customer_name),
            ("phone_invalid", self._phone_invalid),
            ("customer_not_allowed", self._customer_not_allowed),
            ("customer_verification_failed", self._customer_verification_failed),
            (
                "customer_verification_unavailable",
                self._customer_verification_unavailable,
            ),
            ("shop_lookup_unavailable", self._shop_lookup_unavailable),
            ("final_confirmation", self._final_confirmation),
            ("booking_processing", self._booking_processing),
            ("booking_data_incomplete", self._booking_data_incomplete),
            ("booking_failed", self._booking_failed),
            ("booking_complete", self._booking_complete),
            ("booking_cancelled", self._booking_cancelled),
            ("change_ask_shop", self._change_ask_shop),
            ("change_ask_date", self._change_ask_date),
            ("change_ask_people", self._change_ask_people),
            ("change_ask_duration", self._change_ask_duration),
            ("change_ask_course", self._change_ask_course),
            ("change_ask_time", self._change_ask_time),
            ("change_ask_therapist", self._change_ask_therapist),
            ("change_ask_phone", self._change_ask_phone),
            ("change_invalid", self._change_invalid),
        )
        for name, renderer in templates:
            self.register_template(name, renderer)

    @staticmethod
    def _change_ask_shop(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        return DialogResponseDraft("Bạn muốn đổi sang cửa hàng nào?")

    @staticmethod
    def _change_ask_date(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        return DialogResponseDraft("Bạn muốn đổi sang ngày nào?")

    @staticmethod
    def _change_ask_people(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        return DialogResponseDraft("Bạn muốn đổi thành bao nhiêu người?")

    @staticmethod
    def _change_ask_duration(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        return DialogResponseDraft("Bạn muốn đổi sang thời lượng bao nhiêu phút?")

    @staticmethod
    def _change_ask_course(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        return DialogResponseDraft("Bạn muốn đổi sang liệu trình nào?")

    @staticmethod
    def _change_ask_time(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        return DialogResponseDraft("Bạn muốn đổi sang khung giờ nào?")

    @staticmethod
    def _change_ask_therapist(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        return DialogResponseDraft(
            "Bạn muốn chọn Nam, Nữ hay Không yêu cầu?",
            ("Không yêu cầu", "Nam", "Nữ"),
        )

    @staticmethod
    def _change_ask_phone(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        return DialogResponseDraft("Vui lòng nhập số điện thoại mới.")

    @staticmethod
    def _change_invalid(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        return DialogResponseDraft(
            "Thông tin thay đổi chưa hợp lệ. Dữ liệu đặt lịch cũ vẫn được giữ nguyên."
        )

    def _fallback_for_state(
        self,
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        renderer_by_state: dict[BookingState, InstructionRenderer] = {
            BookingState.IDLE: self._greeting,
            BookingState.SELECTING_SHOP: self._ask_shop,
            BookingState.SELECTING_DATE: self._ask_date,
            BookingState.SELECTING_PEOPLE: self._ask_people,
            BookingState.SELECTING_DURATION: self._ask_duration,
            BookingState.SELECTING_SERVICE: self._ask_course,
            BookingState.SELECTING_TIME: self._suggest_time_slots,
            BookingState.SELECTING_THERAPIST: self._ask_therapist,
            BookingState.COLLECTING_PHONE: self._ask_phone,
            BookingState.COLLECTING_NAME: self._ask_customer_name,
            BookingState.AWAITING_CONFIRMATION: self._final_confirmation,
            BookingState.BOOKING_EXECUTING: self._booking_processing,
            BookingState.COMPLETED: self._booking_complete,
            BookingState.BOOKING_FAILED: self._booking_failed,
            BookingState.CANCELLED: self._booking_cancelled,
        }
        return renderer_by_state[result.final_state](context, result)

    @staticmethod
    def _greeting(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        return DialogResponseDraft("Xin chào! Tôi có thể giúp bạn đặt lịch tại cửa hàng.")

    @staticmethod
    def _ask_shop(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        return DialogResponseDraft("Bạn muốn đặt lịch tại cửa hàng nào?")

    @staticmethod
    def _ask_date(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        text = "Bạn muốn đặt lịch vào ngày nào?"
        if context.booking_date is not None:
            text += f" Ngày đang chọn là {_format_date(context.booking_date)}."
        return DialogResponseDraft(text)

    @staticmethod
    def _date_still_unavailable(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        if context.last_unavailable_date is not None:
            return DialogResponseDraft(
                f"Ngày {_format_date(context.last_unavailable_date)} hiện vẫn chưa thể đặt lịch. "
                "Bạn vui lòng chọn một ngày khác."
            )
        return DialogResponseDraft(
            "Ngày này hiện vẫn chưa thể đặt lịch. Bạn vui lòng chọn ngày khác."
        )

    @staticmethod
    def _ask_people(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        return DialogResponseDraft(
            "Bạn muốn đặt lịch cho bao nhiêu người?",
            ("1 người", "2 người", "3 người"),
        )

    @staticmethod
    def _people_too_many(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        return DialogResponseDraft(
            "Hệ thống hiện hỗ trợ tối đa 3 người cho một booking. "
            "Bạn vui lòng chọn từ 1 đến 3 người.",
            ("1 người", "2 người", "3 người"),
        )

    @staticmethod
    def _ask_duration(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        return DialogResponseDraft("Bạn muốn chọn thời lượng bao nhiêu phút?")

    @staticmethod
    def _ask_course(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        text = "Bạn muốn chọn liệu trình chính nào?"
        if context.main_course is not None:
            text = f"Bạn đã chọn {context.main_course.name}. Bạn muốn chọn thêm add-on nào?"
            if context.addons:
                addon_names = ", ".join(item.name for item in context.addons)
                text += f" Add-on đang chọn: {addon_names}."
        return DialogResponseDraft(
            text,
            ("Không chọn add-on",) if context.main_course is not None else (),
            metadata={"has_addons": bool(context.addons)},
        )

    @staticmethod
    def _addon_needs_main(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        return DialogResponseDraft("Vui lòng chọn liệu trình chính trước khi chọn add-on.")

    @staticmethod
    def _main_course_required(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        return DialogResponseDraft("Bạn cần chọn một liệu trình chính để tiếp tục.")

    @staticmethod
    def _combo_not_bookable_retry(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        return DialogResponseDraft(
            "Tổ hợp liệu trình này chưa thể đặt. Vui lòng chọn lại.",
            metadata={"can_retry": True},
        )

    @staticmethod
    def _duration_invalid(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        return DialogResponseDraft("Thời lượng đã chọn không hợp lệ. Vui lòng chọn lại.")

    @staticmethod
    def _no_slots_available(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        return DialogResponseDraft(
            "Ngày đã chọn hiện không còn khung giờ trống. Vui lòng chọn ngày khác."
        )

    @staticmethod
    def _no_working_shift(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        shop_name = context.shop.name if context.shop is not None else "Cửa hàng đã chọn"
        if context.booking_date is not None:
            return DialogResponseDraft(
                f"{shop_name} hiện chưa phục vụ đặt lịch vào ngày "
                f"{_format_date(context.booking_date)}. "
                "Vui lòng chọn ngày khác."
            )
        return DialogResponseDraft(
            f"{shop_name} hiện chưa có lịch phục vụ cho ngày này. Vui lòng chọn ngày khác."
        )

    @staticmethod
    def _slot_api_error(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        return DialogResponseDraft(
            "Chưa thể kiểm tra khung giờ lúc này. Vui lòng thử lại.",
            metadata={"can_retry": True},
        )

    @staticmethod
    def _suggest_time_slots(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        slots = context.available_slots or ()
        return DialogResponseDraft(
            "Bạn muốn chọn khung giờ nào?",
            tuple(_format_time(slot) for slot in slots),
            {"available_slot_count": len(slots)},
        )

    @staticmethod
    def _slot_unavailable(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        return DialogResponseDraft(
            "Khung giờ vừa chọn không còn trống. Vui lòng chọn khung giờ khác.",
            metadata={"can_retry": True},
        )

    @staticmethod
    def _ask_therapist(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        if context.num_customer in (2, 3):
            return DialogResponseDraft(
                "Đặt nhóm không hỗ trợ chọn kỹ thuật viên theo tên. "
                "Bạn có thể yêu cầu giới tính kỹ thuật viên hoặc không yêu cầu.",
                ("Không yêu cầu", "Nam", "Nữ"),
            )
        return DialogResponseDraft(
            "Bạn có thể nhập tên kỹ thuật viên cụ thể, chọn giới tính hoặc bỏ qua.",
            ("Không yêu cầu", "Nam", "Nữ"),
        )

    @staticmethod
    def _therapist_unavailable(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        return DialogResponseDraft("Kỹ thuật viên đã chọn hiện không khả dụng. Vui lòng chọn lại.")

    @staticmethod
    def _ask_phone(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        return DialogResponseDraft("Vui lòng nhập số điện thoại để kiểm tra thông tin khách hàng.")

    @staticmethod
    def _ask_customer_name(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        return DialogResponseDraft(
            "Đây là lần đầu số điện thoại này đặt lịch. Vui lòng cho biết tên khách hàng."
        )

    @staticmethod
    def _phone_invalid(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        return DialogResponseDraft("Số điện thoại chưa hợp lệ. Vui lòng kiểm tra và nhập lại.")

    @staticmethod
    def _customer_not_allowed(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        return DialogResponseDraft(
            "Không thể tiếp tục đặt lịch trực tuyến. Vui lòng liên hệ trực tiếp "
            "cửa hàng để được hỗ trợ."
        )

    @staticmethod
    def _customer_verification_failed(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        return DialogResponseDraft(
            "Chưa thể xác minh thông tin khách hàng. Vui lòng kiểm tra và thử lại.",
            metadata={"can_retry": True},
        )

    @staticmethod
    def _customer_verification_unavailable(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        return DialogResponseDraft(
            "Dịch vụ xác minh khách hàng tạm thời chưa khả dụng. Vui lòng thử lại sau.",
            metadata={"can_retry": True},
        )

    @staticmethod
    def _shop_lookup_unavailable(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        return DialogResponseDraft(
            "Hệ thống chưa thể tải danh sách cửa hàng từ POS lúc này. Vui lòng thử lại.",
            ("Thử lại đặt lịch", "Xem danh sách cửa hàng"),
            {"can_retry": True},
        )

    @staticmethod
    def _final_confirmation(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        lines = (
            "Vui lòng xác nhận thông tin đặt lịch:",
            *_booking_summary_lines(context),
            "",
            "Bạn có muốn xác nhận đặt lịch với thông tin trên không?",
        )
        return DialogResponseDraft(
            "\n".join(lines),
            ("Xác nhận", "Chỉnh sửa", "Hủy"),
            {
                "has_addons": bool(context.addons),
                "can_change_info": True,
            },
        )

    @staticmethod
    def _booking_processing(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        return DialogResponseDraft(
            "Đang kiểm tra và tạo lịch đặt của bạn...",
            metadata={"booking_created": False},
        )

    @staticmethod
    def _booking_data_incomplete(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        return DialogResponseDraft("Thông tin đặt lịch chưa đầy đủ. Vui lòng kiểm tra lại.")

    @staticmethod
    def _booking_failed(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        return DialogResponseDraft(
            "Hệ thống chưa thể tạo lịch lúc này. Vui lòng thử lại hoặc liên hệ cửa hàng.",
            metadata={"booking_created": False, "can_retry": True},
        )

    @staticmethod
    def _booking_complete(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        if result.final_state is not BookingState.COMPLETED or context.booking is None:
            return DialogResponseDraft(
                "Thông tin đặt lịch chưa được xác nhận. Vui lòng thử lại hoặc liên hệ cửa hàng.",
                metadata={"booking_created": False},
            )
        reservation_code = context.booking.reservation_code or context.reservation_code
        lines = ["Đặt lịch thành công!"]
        if reservation_code:
            lines.append(f"Mã đặt lịch: {reservation_code}")
        else:
            lines.append("Thông tin đặt lịch đã được ghi nhận.")
        lines.append("")
        lines.extend(_booking_summary_lines(context))
        return DialogResponseDraft("\n".join(lines), metadata={"booking_created": True})

    @staticmethod
    def _booking_cancelled(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        return DialogResponseDraft("Yêu cầu đặt lịch đã được hủy.")


def _normalize_quick_replies(
    values: Iterable[str],
    *,
    limit: int = 8,
) -> tuple[str, ...]:
    if type(limit) is not int or limit < 0:
        raise ValueError("Quick reply limit must be a non-negative integer.")
    if limit == 0:
        return ()
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            raise TypeError("Quick replies must be strings.")
        item = value.strip()
        if item and item not in seen:
            seen.add(item)
            normalized.append(item)
            if len(normalized) == limit:
                break
    return tuple(normalized)


def _allowlisted_metadata(values: Mapping[str, object]) -> Mapping[str, object]:
    safe: dict[str, object] = {}
    for key, value in values.items():
        if key not in _SAFE_METADATA_KEYS:
            continue
        if key in {"available_slot_count", "item_count", "source_count"}:
            if type(value) is int and value >= 0:
                safe[key] = value
        elif key == "response_type":
            if isinstance(value, str) and value == "faq":
                safe[key] = value
        elif type(value) is bool:
            safe[key] = value
    return MappingProxyType(safe)


def _format_date(value: date) -> str:
    return value.strftime("%d/%m/%Y")


def _format_time(value: time) -> str:
    return value.strftime("%H:%M")


def _shop_name(context: BookingContext) -> str:
    return context.shop.name if context.shop is not None else "chưa chọn"


def _date_text(context: BookingContext) -> str:
    return _format_date(context.booking_date) if context.booking_date else "chưa chọn"


def _time_text(context: BookingContext) -> str:
    return _format_time(context.start_time) if context.start_time else "chưa chọn"


def _people_text(context: BookingContext) -> str:
    return str(context.num_customer) if context.num_customer is not None else "chưa chọn"


def _duration_text(context: BookingContext) -> str:
    if context.duration_minutes is None:
        return "chưa chọn"
    return f"{context.duration_minutes} phút"


def _course_name(context: BookingContext) -> str:
    return context.main_course.name if context.main_course is not None else "chưa chọn"


def _addon_text(context: BookingContext) -> str:
    return ", ".join(addon.name for addon in context.addons) or "Không"


def _therapist_text(context: BookingContext) -> str:
    preference = context.therapist_preference
    if preference is None or preference.preference_type is TherapistPreferenceType.NONE:
        return "Không yêu cầu"
    if preference.preference_type is TherapistPreferenceType.MALE:
        return "Ưu tiên kỹ thuật viên nam"
    if preference.preference_type is TherapistPreferenceType.FEMALE:
        return "Ưu tiên kỹ thuật viên nữ"
    return preference.therapist_name or "Kỹ thuật viên đã chọn"


def _full_phone_text(context: BookingContext) -> str:
    return context.phone if context.phone is not None else "chưa có"


def _customer_name_text(context: BookingContext) -> str:
    return context.customer_name or "chưa có"


def _booking_summary_lines(context: BookingContext) -> tuple[str, ...]:
    return (
        f"Tên khách hàng: {_customer_name_text(context)}",
        f"Số điện thoại: {_full_phone_text(context)}",
        f"Cửa hàng: {_shop_name(context)}",
        f"Ngày: {_date_text(context)}",
        f"Giờ: {_time_text(context)}",
        f"Số người: {_people_text(context)}",
        f"Thời lượng: {_duration_text(context)}",
        f"Liệu trình: {_course_name(context)}",
        f"Add-on: {_addon_text(context)}",
        f"Kỹ thuật viên: {_therapist_text(context)}",
    )
