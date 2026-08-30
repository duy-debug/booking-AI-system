"""Build deterministic, transport-neutral responses from dialog turn results."""

import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, time
from types import MappingProxyType
from typing import TypeAlias

from app.dialog.dialog_controller import DialogTurnResult, DialogTurnStatus
from app.domain.booking_context import BookingContext
from app.domain.booking_models import (
    MAX_CUSTOMERS_PER_BOOKING,
    MIN_CUSTOMERS_PER_BOOKING,
    TherapistPreferenceType,
)
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
        "faq_answer",
        "next_question",
        "source_count",
        "item_count",
        "preserve_structured_text",
    }
)
_UNHANDLED_FAILURE_TEXT = "Đã có lỗi xảy ra. Vui lòng thử lại hoặc liên hệ cửa hàng."


# Nhóm lỗi instruction giúp fail fast khi template flow khai báo sai hoặc renderer trả sai contract.
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


# Draft là output deterministic từ template trước khi ResponseGenerator
# có thể diễn đạt lại bằng LLM.
@dataclass(frozen=True, slots=True)
class DialogResponseDraft:
    """Contains presentation data produced by one instruction renderer."""

    text: str
    metadata: Mapping[str, object] = field(default_factory=dict)

    # Response draft không được rỗng vì transport luôn cần text để frontend render.
    def __post_init__(self) -> None:
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError("Dialog response draft text must not be empty.")
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


# DialogResponse là contract public nội bộ giữa dialog layer và transport/SSE.
@dataclass(frozen=True, slots=True)
class DialogResponse:
    """Represents a rendered response independent of HTTP and streaming concerns."""

    text: str
    instruction_template: str | None
    state: BookingState
    status: DialogTurnStatus
    metadata: Mapping[str, object] = field(default_factory=dict)

    # Metadata chỉ được giữ các key an toàn để không lộ internal context ra frontend.
    def __post_init__(self) -> None:
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError("Dialog response text must not be empty.")
        object.__setattr__(self, "metadata", _allowlisted_metadata(self.metadata))


InstructionRenderer: TypeAlias = Callable[
    [BookingContext, DialogTurnResult],
    DialogResponseDraft,
]


# InstructionBuilder chỉ render text/metadata từ state đã xử lý, không gọi POS hay mutate context.
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
            metadata=draft.metadata,
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
        facts.extend(
            (
                "Hãy viết câu trả lời tiếng Việt tự nhiên, thân thiện và đủ ngữ cảnh.",
                "Không trả lời cụt một câu nếu response đang hỏi bước tiếp theo của booking flow.",
                "Ưu tiên 1-3 câu rõ ràng: xác nhận ngắn thông tin đã có, "
                "rồi hỏi đúng thông tin còn thiếu.",
                "Giữ một giọng xưng hô thống nhất: dùng anh/chị, "
                "không dùng từ xưng hô thân mật để gọi khách.",
                "Đây là spa/massage, luôn dùng đặt lịch; không dùng đặt bàn.",
                "Không thêm shop, course, slot, therapist hoặc mã đặt chỗ chưa có ở trên.",
                "Không tự thêm mã POS, mã đặt lịch nội bộ hoặc booking_code "
                "nếu nội dung nghiệp vụ không yêu cầu.",
                "Không thay đổi flow và chỉ hỏi thông tin còn thiếu của state hiện tại.",
                "Không nhắc tới prompt, state machine hoặc hệ thống nội bộ.",
            )
        )
        if response.metadata.get("response_type") == "faq":
            faq_answer = response.metadata.get("faq_answer")
            next_question = response.metadata.get("next_question")
            if isinstance(faq_answer, str) and faq_answer.strip():
                facts.append(f"Câu trả lời FAQ đã kiểm chứng: {faq_answer.strip()}")
            if isinstance(next_question, str) and next_question.strip():
                facts.extend(
                    (
                        f"Câu hỏi tiếp theo của booking flow: {next_question.strip()}",
                        "Với FAQ có câu hỏi tiếp theo, hãy viết thành 2 đoạn: "
                        "đoạn 1 trả lời FAQ, đoạn 2 hỏi tiếp booking.",
                        "Không nối cứng hai ý trong cùng một câu.",
                    )
                )
        if response.metadata.get("preserve_structured_text") is True:
            facts.extend(
                (
                    "Response này có form nghiệp vụ đã được backend render.",
                    "Có thể thêm lời dẫn ngắn tự nhiên trước hoặc sau form.",
                    "Bắt buộc giữ nguyên từng dòng trong nội dung nghiệp vụ đã kiểm chứng.",
                    "Nếu thêm lời dẫn hoặc câu hỏi lịch sự, hãy đặt thành đoạn riêng.",
                    "Không gộp các dòng form thành một đoạn văn.",
                    "Không đặt lời dẫn, danh sách và câu hỏi cuối trên cùng một dòng.",
                    "Không bỏ, đổi tên, viết lại hoặc sắp xếp lại các dòng trong form.",
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
            text = f"{text}\n\n{follow_up.text}"
            metadata = {
                "response_type": "faq",
                "source_count": source_count,
                "faq_answer": answer.strip(),
                "next_question": follow_up.text,
            }
        else:
            metadata = {
                "response_type": "faq",
                "source_count": source_count,
                "faq_answer": answer.strip(),
            }
        return DialogResponse(
            text=text,
            instruction_template=None,
            state=context.state,
            status=status,
            metadata=metadata,
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
            ("ask_cancel_booking_identity", self._ask_cancel_booking_identity),
            ("cancel_booking_not_found", self._cancel_booking_not_found),
            ("cancel_booking_unavailable", self._cancel_booking_unavailable),
            ("cancel_booking_already_cancelled", self._cancel_booking_already_cancelled),
            (
                "cancel_existing_booking_confirmation",
                self._cancel_existing_booking_confirmation,
            ),
            ("change_ask_shop", self._change_ask_shop),
            ("change_ask_date", self._change_ask_date),
            ("change_ask_people", self._change_ask_people),
            ("change_ask_duration", self._change_ask_duration),
            ("change_ask_course", self._change_ask_course),
            ("change_ask_addon", self._change_ask_addon),
            ("change_ask_time", self._change_ask_time),
            ("change_ask_therapist", self._change_ask_therapist),
            ("change_ask_phone", self._change_ask_phone),
            ("change_ask_customer_name", self._change_ask_customer_name),
            ("change_invalid", self._change_invalid),
        )
        for name, renderer in templates:
            self.register_template(name, renderer)

    @staticmethod
    def _change_ask_shop(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        return DialogResponseDraft(
            "Anh/chị muốn đổi lịch sang cửa hàng nào? "
            "Anh/chị có thể nhập tên chi nhánh hoặc khu vực để mình kiểm tra lại lựa chọn phù hợp."
        )

    @staticmethod
    def _change_ask_date(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        return DialogResponseDraft(
            "Anh/chị muốn đổi lịch sang ngày nào? "
            "Anh/chị có thể nhập hôm nay, ngày mai hoặc một ngày cụ thể "
            "để mình kiểm tra lịch trống."
        )

    @staticmethod
    def _change_ask_people(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        return DialogResponseDraft(
            "Anh/chị muốn đổi lịch thành bao nhiêu người? "
            "Mình sẽ kiểm tra lại theo giới hạn đặt lịch hiện tại trước khi xác nhận thay đổi."
        )

    @staticmethod
    def _change_ask_duration(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        return DialogResponseDraft(
            "Anh/chị muốn đổi sang thời lượng bao nhiêu phút? "
            "Mình sẽ đối chiếu với các thời lượng mà cửa hàng đang hỗ trợ."
        )

    @staticmethod
    def _change_ask_course(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        return DialogResponseDraft(
            "Anh/chị muốn đổi sang liệu trình nào? "
            "Anh/chị có thể nhập tên liệu trình mong muốn để mình kiểm tra lại khả dụng."
        )

    @staticmethod
    def _change_ask_addon(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        return DialogResponseDraft(
            "Anh/chị muốn đổi dịch vụ đi kèm như thế nào? "
            "Anh/chị có thể chọn add-on mới hoặc báo không chọn add-on "
            "để mình kiểm tra lại lịch trống."
        )

    @staticmethod
    def _change_ask_time(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        return DialogResponseDraft(
            "Anh/chị muốn đổi sang khung giờ nào? "
            "Mình sẽ kiểm tra lại khung giờ đó với cửa hàng và kỹ thuật viên nếu có."
        )

    @staticmethod
    def _change_ask_therapist(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        return DialogResponseDraft(
            "Anh/chị muốn đổi yêu cầu kỹ thuật viên như thế nào? "
            "Anh/chị có thể chọn Không yêu cầu, chọn giới tính hoặc nhập tên kỹ thuật viên cụ thể.",
            ("Không yêu cầu", "Nam", "Nữ"),
        )

    @staticmethod
    def _change_ask_phone(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        return DialogResponseDraft(
            "Anh/chị vui lòng nhập số điện thoại mới để mình kiểm tra thông tin khách hàng "
            "trước khi cập nhật lịch."
        )

    @staticmethod
    def _change_ask_customer_name(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        return DialogResponseDraft(
            "Anh/chị vui lòng nhập tên khách hàng mới để mình cập nhật lại thông tin xác nhận."
        )

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
            BookingState.COLLECTING_CANCEL_BOOKING_IDENTITY: self._ask_cancel_booking_identity,
            BookingState.AWAITING_CANCEL_CONFIRMATION: self._cancel_existing_booking_confirmation,
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
        return DialogResponseDraft(
            "Xin chào anh/chị, mình là Kori. "
            "Mình có thể hỗ trợ anh/chị đặt lịch mới, điều chỉnh lịch đang tạo "
            "hoặc hủy booking đã đặt."
        )

    @staticmethod
    def _ask_shop(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        return DialogResponseDraft(
            "Anh/chị muốn đặt lịch tại cửa hàng hoặc khu vực nào? "
            "Anh/chị có thể nhập tên chi nhánh, ví dụ Komorebi Nha Trang, để mình kiểm tra tiếp."
        )

    @staticmethod
    def _ask_date(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        if context.shop is not None:
            text = (
                f"Mình đã ghi nhận cửa hàng {context.shop.name}. "
                "Anh/chị muốn đặt lịch vào ngày nào?"
            )
        else:
            text = "Anh/chị muốn đặt lịch vào ngày nào?"
        if context.booking_date is not None:
            text += f" Ngày đang chọn là {_format_date(context.booking_date)}."
        text += (
            " Anh/chị có thể nhập hôm nay, ngày mai hoặc một ngày cụ thể "
            "để mình kiểm tra lịch trống phù hợp."
        )
        return DialogResponseDraft(text)

    @staticmethod
    def _date_still_unavailable(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        if context.last_unavailable_date is not None:
            return DialogResponseDraft(
                f"Ngày {_format_date(context.last_unavailable_date)} hiện vẫn chưa thể đặt lịch. "
                "Anh/chị vui lòng chọn một ngày khác."
            )
        return DialogResponseDraft(
            "Ngày này hiện vẫn chưa thể đặt lịch. Anh/chị vui lòng chọn ngày khác."
        )

    @staticmethod
    def _ask_people(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        details: list[str] = []
        if context.shop is not None:
            details.append(f"tại {context.shop.name}")
        if context.booking_date is not None:
            details.append(f"ngày {_format_date(context.booking_date)}")
        prefix = f"Mình đã ghi nhận lịch {' '.join(details)}. " if details else ""
        return DialogResponseDraft(
            prefix
            + "Anh/chị muốn đặt lịch cho bao nhiêu người? "
            + "Hiện hệ thống hỗ trợ từ "
            + f"{MIN_CUSTOMERS_PER_BOOKING} đến {MAX_CUSTOMERS_PER_BOOKING} người cho một booking."
        )

    @staticmethod
    def _people_too_many(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        return DialogResponseDraft(
            "Số người đã chọn chưa hợp lệ. "
            "Anh/chị vui lòng chọn theo gợi ý hợp lệ bên dưới.",
        )

    @staticmethod
    def _ask_duration(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        details: list[str] = []
        if context.shop is not None:
            details.append(context.shop.name)
        if context.num_customer is not None:
            details.append(f"{context.num_customer} người")
        prefix = f"Với thông tin đã chọn ({', '.join(details)}), " if details else ""
        return DialogResponseDraft(
            prefix
            + "anh/chị muốn chọn thời lượng bao nhiêu phút? "
            + "Mình sẽ dựa trên dữ liệu thật của cửa hàng để gợi ý các thời lượng đang hỗ trợ."
        )

    @staticmethod
    def _ask_course(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        text = (
            "Anh/chị muốn chọn liệu trình chính nào? "
            "Anh/chị có thể nhập tên liệu trình hoặc chọn trong danh sách mình gợi ý."
        )
        if context.main_course is not None:
            text = (
                f"Anh/chị đã chọn liệu trình chính {context.main_course.name}. "
                "Anh/chị muốn chọn thêm add-on nào, hay bỏ qua bước add-on để tiếp tục?"
            )
            if context.addons:
                addon_names = ", ".join(item.name for item in context.addons)
                text += f" Add-on đang chọn: {addon_names}."
        return DialogResponseDraft(
            text,
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
        return DialogResponseDraft(
            "Anh/chị cần chọn một liệu trình chính trước để mình kiểm tra thời lượng, "
            "khung giờ và các add-on phù hợp."
        )

    @staticmethod
    def _combo_not_bookable_retry(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        return DialogResponseDraft(
            "Tổ hợp liệu trình hiện tại chưa thể đặt ở cửa hàng đã chọn. "
            "Anh/chị vui lòng chọn lại liệu trình hoặc add-on khác để mình kiểm tra tiếp.",
            metadata={"can_retry": True},
        )

    @staticmethod
    def _duration_invalid(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        return DialogResponseDraft(
            "Thời lượng đã chọn không hợp lệ. "
            "Anh/chị vui lòng chọn thời lượng theo gợi ý hợp lệ của cửa hàng bên dưới.",
        )

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
            "Mình đã kiểm tra được các khung giờ còn trống. "
            "Anh/chị muốn chọn khung giờ nào để tiếp tục đặt lịch?",
            metadata={
                "available_slot_count": len(slots),
                "preserve_structured_text": True,
            },
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
                "Với booking nhóm, hệ thống chưa hỗ trợ chọn kỹ thuật viên theo tên riêng. "
                "Anh/chị có thể chọn giới tính kỹ thuật viên Nam/Nữ hoặc chọn Không yêu cầu "
                "để cửa hàng sắp xếp phù hợp.",
            )
        return DialogResponseDraft(
            "Anh/chị muốn chọn kỹ thuật viên như thế nào? "
            "Anh/chị có thể nhập tên kỹ thuật viên cụ thể, chọn giới tính hoặc chọn Không yêu cầu.",
        )

    @staticmethod
    def _therapist_unavailable(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        return DialogResponseDraft(
            "Kỹ thuật viên đã chọn hiện không còn trống ở khung giờ mới. "
            "Anh/chị có thể chọn Không yêu cầu hoặc chọn kỹ thuật viên khác.",
        )

    @staticmethod
    def _ask_phone(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        return DialogResponseDraft(
            "Anh/chị vui lòng nhập số điện thoại để mình kiểm tra thông tin khách hàng "
            "và hoàn tất bước xác nhận lịch."
        )

    @staticmethod
    def _ask_customer_name(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        return DialogResponseDraft(
            "Mình chưa có tên khách hàng cho số điện thoại này. "
            "Anh/chị vui lòng cho mình biết tên khách hàng để lưu vào thông tin đặt lịch."
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
            "Số điện thoại anh/chị vừa cung cấp hiện đang bị hạn chế đặt lịch "
            "trực tuyến trên hệ thống. Anh/chị có thể kiểm tra lại số điện thoại, "
            "dùng số điện thoại khác hoặc liên hệ trực tiếp cửa hàng để được hỗ trợ."
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
            metadata={"can_retry": True},
        )

    @staticmethod
    # Form xác nhận cuối là dữ liệu nghiệp vụ đã validate nên cần giữ nguyên từng dòng khi qua NLG.
    def _final_confirmation(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        lines = (
            "Vui lòng xác nhận thông tin đặt lịch:",
            *_booking_summary_lines(context),
            "",
            "Anh/chị có muốn xác nhận đặt lịch với thông tin trên không?",
        )
        return DialogResponseDraft(
            "\n".join(lines),
            metadata={
                "has_addons": bool(context.addons),
                "can_change_info": True,
                "preserve_structured_text": True,
            },
        )

    @staticmethod
    def _booking_processing(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        return DialogResponseDraft(
            "Đang kiểm tra và tạo lịch đặt của anh/chị...",
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
    # Booking complete hiển thị mã đặt lịch và summary đã commit từ POS,
    # không được để LLM làm mất field.
    def _booking_complete(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        if result.final_state is not BookingState.COMPLETED or context.booking is None:
            return DialogResponseDraft(
                "Thông tin đặt lịch chưa được xác nhận. Vui lòng thử lại hoặc liên hệ cửa hàng.",
                metadata={"booking_created": False},
            )
        # Ưu tiên mã đã được application chuẩn hóa trước khi fallback về dữ liệu booking gốc.
        reservation_code = context.reservation_code or context.booking.reservation_code
        lines = ["Đặt lịch thành công!"]
        if reservation_code:
            lines.append(f"Mã đặt lịch: {reservation_code}")
        else:
            lines.append("Thông tin đặt lịch đã được ghi nhận.")
        lines.append("")
        lines.extend(_booking_summary_lines(context))
        lines.append("")
        lines.append("Cảm ơn anh/chị đã tin tưởng và lựa chọn Komorebi.")
        return DialogResponseDraft(
            "\n".join(lines),
            metadata={
                "booking_created": True,
                "preserve_structured_text": True,
            },
        )

    @staticmethod
    def _booking_cancelled(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        if context.booking is not None and context.booking.status == "cancelled":
            return InstructionBuilder._existing_booking_cancelled(context, result)
        return DialogResponseDraft("Yêu cầu đặt lịch đã được hủy.")

    @staticmethod
    def _ask_cancel_booking_identity(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        missing_parts: list[str] = []
        if context.cancel_booking_reference is None:
            missing_parts.append("mã booking")
        if context.phone is None:
            missing_parts.append("số điện thoại đã đặt lịch")
        if missing_parts:
            missing_text = " và ".join(missing_parts)
            return DialogResponseDraft(
                f"Để hủy booking đã đặt, anh/chị vui lòng cung cấp {missing_text}."
            )
        return DialogResponseDraft(
            "Anh/chị vui lòng gửi lại mã booking và số điện thoại đã đặt lịch để em kiểm tra."
        )

    @staticmethod
    def _cancel_booking_not_found(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        return DialogResponseDraft(
            "Em chưa tìm thấy booking khớp với mã booking và số điện thoại anh/chị vừa cung cấp. "
            "Anh/chị vui lòng kiểm tra lại thông tin giúp em nhé."
        )

    @staticmethod
    def _cancel_booking_unavailable(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        return DialogResponseDraft(
            "Hiện tại hệ thống chưa thể kiểm tra hoặc hủy booking này. "
            "Anh/chị vui lòng thử lại sau hoặc liên hệ trực tiếp cửa hàng để được hỗ trợ."
        )

    @staticmethod
    def _cancel_booking_already_cancelled(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        return DialogResponseDraft("Booking này đã được hủy trước đó rồi ạ.")

    @staticmethod
    # Bước này chỉ xác nhận ý định hủy sau lookup, chưa thực hiện side effect cancel booking.
    def _cancel_existing_booking_confirmation(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        if context.booking is None:
            return DialogResponseDraft(
                "Em đã nhận yêu cầu hủy booking. "
                "Anh/chị vui lòng cung cấp mã booking và số điện thoại để em kiểm tra trước nhé."
            )

        # Chỉ hiển thị thông tin đã lookup từ POS, chưa gọi API hủy ở bước này.
        lines = [
            "Em đã tìm thấy booking sau. Anh/chị vui lòng kiểm tra lại trước khi hủy:"
        ]
        lines.extend(_booking_reference_lines(context))
        lines.append("")
        lines.extend(_booking_summary_lines(context))
        lines.append("")
        lines.append("Anh/chị có chắc chắn muốn hủy booking này không?")
        return DialogResponseDraft(
            "\n".join(lines),
            metadata={
                "requires_cancel_confirmation": True,
                "preserve_structured_text": True,
            },
        )

    @staticmethod
    def _cancel_existing_booking_declined(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        return DialogResponseDraft(
            "Em chưa hủy booking này. "
            "Nếu anh/chị cần đặt lịch mới hoặc hủy booking khác, cứ nhắn em nhé."
        )

    @staticmethod
    # Sau khi POS hủy thành công, response phải giữ thông tin booking đã hủy để khách đối chiếu.
    def _existing_booking_cancelled(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        lines = ["Hủy booking thành công!"]
        lines.extend(_booking_reference_lines(context))
        lines.append("")
        lines.extend(_booking_summary_lines(context))
        lines.append("")
        lines.append("Cảm ơn anh/chị đã tin tưởng và lựa chọn Komorebi.")
        lines.append("")
        lines.append("Anh/chị có cần em hỗ trợ đặt lịch mới hoặc hủy booking khác không ạ?")
        return DialogResponseDraft(
            "\n".join(lines),
            metadata={
                "booking_cancelled": True,
                "preserve_structured_text": True,
            },
        )




# Lọc metadata từ template để chỉ field được frontend/NLG tin cậy mới đi qua response public.
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
        elif key in {"faq_answer", "next_question"}:
            if isinstance(value, str) and value.strip():
                safe[key] = value.strip()
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


def _booking_reference_lines(context: BookingContext) -> tuple[str, ...]:
    lines: list[str] = []
    booking_id = context.booking_id
    if booking_id is None and context.booking is not None:
        booking_id = context.booking.booking_id
    if booking_id is not None:
        lines.append(f"Mã booking: {booking_id}")
    return tuple(lines)
