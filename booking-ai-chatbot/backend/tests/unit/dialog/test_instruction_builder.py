"""Tests for deterministic dialog instruction rendering."""

from copy import deepcopy
from datetime import date, time
from decimal import Decimal
from types import MappingProxyType
from uuid import UUID

import pytest

from app.dialog.dialog_controller import DialogTurnResult, DialogTurnStatus
from app.dialog.instruction_builder import (
    DialogResponseDraft,
    DuplicateInstructionTemplateError,
    InstructionBuilder,
    InstructionRenderingError,
    InvalidInstructionTemplateNameError,
    UnknownInstructionTemplateError,
)
from app.domain.booking_context import BookingContext
from app.domain.booking_models import (
    Booking,
    Course,
    CourseType,
    Customer,
    Shop,
    TherapistPreference,
    TherapistPreferenceType,
)
from app.domain.booking_state import BookingState

SHOP = Shop(UUID("11111111-1111-1111-1111-111111111111"), "Sen Spa")
COURSE = Course(
    UUID("22222222-2222-2222-2222-222222222222"),
    "Massage thư giãn",
    60,
    Decimal("500000"),
)
ADDON = Course(
    UUID("33333333-3333-3333-3333-333333333333"),
    "Đá nóng",
    15,
    Decimal("100000"),
    CourseType.ADDON,
)
CUSTOMER = Customer("0901234567", "An")
BOOKING_ID = UUID("44444444-4444-4444-4444-444444444444")


def turn_result(
    template: str | None,
    state: BookingState,
    status: DialogTurnStatus = DialogTurnStatus.SUCCESS,
) -> DialogTurnResult:
    return DialogTurnResult(
        status=status,
        initial_state=BookingState.IDLE,
        final_state=state,
        intent="test",
        instruction_template=template,
        executed_actions=(),
        auto_transition_count=0,
    )


def ready_context(
    *,
    state: BookingState = BookingState.AWAITING_CONFIRMATION,
) -> BookingContext:
    return BookingContext(
        conversation_id="conversation-1",
        state=state,
        shop=SHOP,
        main_course=COURSE,
        customer=CUSTOMER,
        booking_date=date(2026, 8, 2),
        start_time=time(10, 30),
        num_customer=1,
        duration_minutes=75,
        addons=(ADDON,),
        phone=CUSTOMER.phone,
        phone_confirmed=True,
        ng_list_checked=True,
    )


def booking(reservation_code: str | None = None, *, status: str = "confirmed") -> Booking:
    return Booking(
        booking_id=BOOKING_ID,
        status=status,
        shop=SHOP,
        main_course=COURSE,
        customer=CUSTOMER,
        booking_date=date(2026, 8, 2),
        start_time=time(10, 30),
        duration_minutes=75,
        addons=(ADDON,),
        reservation_code=reservation_code,
    )


def test_register_template_preserves_insertion_order_and_custom_renderer() -> None:
    builder = InstructionBuilder()

    builder.register_template(
        "custom_message",
        lambda context, result: DialogResponseDraft("Nội dung tùy chỉnh."),
    )

    assert builder.registered_templates()[-1] == "custom_message"
    response = builder.build_response(
        result=turn_result("custom_message", BookingState.IDLE),
        context=BookingContext("conversation-1"),
    )
    assert response.text == "Nội dung tùy chỉnh."


def test_duplicate_template_is_rejected() -> None:
    builder = InstructionBuilder()

    with pytest.raises(DuplicateInstructionTemplateError):
        builder.register_template(
            "ask_shop",
            lambda context, result: DialogResponseDraft("Khác."),
        )


@pytest.mark.parametrize("name", ["", " ", "AskShop", "ask-shop", "1_template"])
def test_invalid_template_name_is_rejected(name: str) -> None:
    with pytest.raises(InvalidInstructionTemplateNameError):
        InstructionBuilder().register_template(
            name,
            lambda context, result: DialogResponseDraft("Nội dung."),
        )


def test_unknown_template_is_rejected() -> None:
    with pytest.raises(UnknownInstructionTemplateError):
        InstructionBuilder().build_response(
            result=turn_result("missing_template", BookingState.IDLE),
            context=BookingContext("conversation-1"),
        )


def test_registry_is_isolated_between_instances() -> None:
    first = InstructionBuilder()
    second = InstructionBuilder()
    first.register_template(
        "first_only",
        lambda context, result: DialogResponseDraft("Chỉ instance đầu."),
    )

    assert first.has_template("first_only")
    assert not second.has_template("first_only")


def test_find_missing_templates_deduplicates_in_declared_order() -> None:
    missing = InstructionBuilder().find_missing_templates(
        ("ask_shop", "not_ready", "not_ready", "another_missing")
    )

    assert missing == ("not_ready", "another_missing")


def test_people_renderer_uses_text_only_recovery() -> None:
    response = InstructionBuilder().build_response(
        result=turn_result("ask_people", BookingState.SELECTING_PEOPLE),
        context=BookingContext("conversation-1"),
    )

    assert "từ 1 đến 3 người" in response.text


def test_duration_renderer_uses_text_only_recovery() -> None:
    response = InstructionBuilder().build_response(
        result=turn_result("duration_invalid", BookingState.SELECTING_DURATION),
        context=BookingContext("conversation-1"),
    )

    assert "gợi ý hợp lệ của cửa hàng" in response.text


def test_time_slots_keep_pos_order_and_are_not_limited() -> None:
    slots = tuple(time(8 + index // 4, index % 4 * 15) for index in range(10))
    context = BookingContext("conversation-1", available_slots=slots)

    response = InstructionBuilder().build_response(
        result=turn_result("suggest_time_slots", BookingState.SELECTING_TIME),
        context=context,
    )

    assert "khung giờ còn trống" in response.text
    assert response.metadata == {
        "available_slot_count": len(slots),
        "preserve_structured_text": True,
    }


def test_group_therapist_renderer_offers_gender_but_not_names() -> None:
    context = BookingContext("conversation-1", num_customer=2)

    response = InstructionBuilder().build_response(
        result=turn_result("ask_therapist", BookingState.SELECTING_THERAPIST),
        context=context,
    )

    assert "chưa hỗ trợ chọn kỹ thuật viên theo tên riêng" in response.text
    assert "Không yêu cầu" in response.text
    assert "Nam" in response.text
    assert "Nữ" in response.text


def test_confirmation_summary_formats_context_without_internal_identifiers() -> None:
    context = ready_context()
    context.therapist_preference = TherapistPreference(TherapistPreferenceType.FEMALE)

    response = InstructionBuilder().build_response(
        result=turn_result("final_confirmation", BookingState.AWAITING_CONFIRMATION),
        context=context,
    )

    assert "Sen Spa" in response.text
    assert "02/08/2026" in response.text
    assert "10:30" in response.text
    assert "Tên khách hàng: An" in response.text
    assert "Số điện thoại: 0901234567" in response.text
    assert "Massage thư giãn" in response.text
    assert "Đá nóng" in response.text
    assert "Kỹ thuật viên: Ưu tiên kỹ thuật viên nữ" in response.text
    assert "******" not in response.text
    assert str(BOOKING_ID) not in response.text
    assert response.metadata["preserve_structured_text"] is True


def test_completed_response_prefers_context_display_code() -> None:
    context = ready_context(state=BookingState.COMPLETED)
    context.booking = booking("RSV-2026-001")
    context.reservation_code = str(BOOKING_ID)

    response = InstructionBuilder().build_response(
        result=turn_result("booking_complete", BookingState.COMPLETED),
        context=context,
    )

    assert "Đặt lịch thành công" in response.text
    assert str(BOOKING_ID) in response.text
    assert "RSV-2026-001" not in response.text
    assert "Tên khách hàng: An" in response.text
    assert "Số điện thoại: 0901234567" in response.text
    assert response.metadata == {
        "booking_created": True,
        "preserve_structured_text": True,
    }


def test_completed_response_without_context_code_falls_back_to_booking_code() -> None:
    context = ready_context(state=BookingState.COMPLETED)
    context.booking = booking("RSV-2026-001")

    response = InstructionBuilder().build_response(
        result=turn_result("booking_complete", BookingState.COMPLETED),
        context=context,
    )

    assert "Mã đặt lịch" in response.text
    assert "RSV-2026-001" in response.text
    assert "Tên khách hàng: An" in response.text
    assert str(BOOKING_ID) not in response.text


def test_cancel_confirmation_preserves_structured_booking_form() -> None:
    context = ready_context()
    context.booking = booking("RSV-2026-001")

    response = InstructionBuilder().build_response(
        result=turn_result(
            "cancel_existing_booking_confirmation",
            BookingState.AWAITING_CANCEL_CONFIRMATION,
        ),
        context=context,
    )

    assert "Em đã tìm thấy booking sau" in response.text
    assert "Tên khách hàng: An" in response.text
    assert "Anh/chị có chắc chắn muốn hủy booking này không?" in response.text
    assert response.metadata["preserve_structured_text"] is True


def test_cancel_complete_preserves_structured_booking_form() -> None:
    context = ready_context(state=BookingState.CANCELLED)
    context.booking = booking("RSV-2026-001", status="cancelled")

    response = InstructionBuilder().build_response(
        result=turn_result("booking_cancelled", BookingState.CANCELLED),
        context=context,
    )

    assert "Hủy booking thành công" in response.text
    assert "Tên khách hàng: An" in response.text
    assert "Anh/chị có cần em hỗ trợ đặt lịch mới hoặc hủy booking khác không ạ?" in response.text
    assert response.metadata == {"preserve_structured_text": True}


def test_completed_state_without_booking_does_not_claim_success() -> None:
    response = InstructionBuilder().build_response(
        result=turn_result("booking_complete", BookingState.COMPLETED),
        context=BookingContext("conversation-1", state=BookingState.COMPLETED),
    )

    assert "Đặt lịch thành công" not in response.text
    assert response.metadata == {"booking_created": False}


def test_handled_failure_uses_declared_failure_template() -> None:
    response = InstructionBuilder().build_response(
        result=turn_result(
            "slot_unavailable",
            BookingState.SELECTING_TIME,
            DialogTurnStatus.FAILURE_HANDLED,
        ),
        context=BookingContext("conversation-1"),
    )

    assert "không còn trống" in response.text
    assert response.status is DialogTurnStatus.FAILURE_HANDLED


def test_unhandled_failure_is_always_generic_and_hides_original_metadata() -> None:
    response = InstructionBuilder().build_response(
        result=turn_result(
            "booking_complete",
            BookingState.BOOKING_FAILED,
            DialogTurnStatus.FAILURE_UNHANDLED,
        ),
        context=BookingContext("conversation-1"),
    )

    assert response.text == "Đã có lỗi xảy ra. Vui lòng thử lại hoặc liên hệ cửa hàng."
    assert "booking" not in response.metadata


def test_none_template_uses_state_fallback() -> None:
    response = InstructionBuilder().build_response(
        result=turn_result(None, BookingState.SELECTING_DATE),
        context=BookingContext("conversation-1"),
    )

    assert response.text == (
        "Anh/chị muốn đặt lịch vào ngày nào? "
        "Anh/chị có thể nhập hôm nay, ngày mai hoặc một ngày cụ thể "
        "để mình kiểm tra lịch trống phù hợp."
    )
    assert response.instruction_template is None


def test_renderer_error_is_chained_without_sensitive_value_in_message() -> None:
    builder = InstructionBuilder()
    sensitive = RuntimeError("token=secret")

    def broken_renderer(
        context: BookingContext,
        result: DialogTurnResult,
    ) -> DialogResponseDraft:
        raise sensitive

    builder.register_template("broken_renderer", broken_renderer)

    with pytest.raises(InstructionRenderingError) as captured:
        builder.build_response(
            result=turn_result("broken_renderer", BookingState.IDLE),
            context=BookingContext("conversation-1"),
        )

    assert captured.value.__cause__ is sensitive
    assert "secret" not in str(captured.value)


def test_build_response_does_not_mutate_context() -> None:
    context = ready_context()
    snapshot = deepcopy(context)

    InstructionBuilder().build_response(
        result=turn_result("final_confirmation", BookingState.AWAITING_CONFIRMATION),
        context=context,
    )

    assert context == snapshot


def test_metadata_is_immutable_and_filters_sensitive_or_invalid_values() -> None:
    builder = InstructionBuilder()
    builder.register_template(
        "unsafe_metadata",
        lambda context, result: DialogResponseDraft(
            "Nội dung an toàn.",
            metadata={
                "booking_created": True,
                "available_slot_count": "secret",
                "raw_phone": "0901234567",
                "exception": RuntimeError("secret"),
            },
        ),
    )

    response = builder.build_response(
        result=turn_result("unsafe_metadata", BookingState.IDLE),
        context=BookingContext("conversation-1"),
    )

    assert response.metadata == {"booking_created": True}
    assert isinstance(response.metadata, MappingProxyType)
    with pytest.raises(TypeError):
        response.metadata["booking_created"] = False  # type: ignore[index]
