"""Integration tests between the real booking flow and response renderers."""

from datetime import date, time
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from app.dialog.dialog_controller import DialogTurnResult, DialogTurnStatus
from app.dialog.flow_loader import FlowDefinition, FlowLoader
from app.dialog.instruction_builder import InstructionBuilder
from app.domain.booking_context import BookingContext
from app.domain.booking_models import Booking, Course, Customer, Shop
from app.domain.booking_state import BookingState

FLOW_PATH = Path(__file__).resolve().parents[3] / "app" / "dialog" / "booking_flow.json"
CHANGE_HANDLERS_PATH = FLOW_PATH
SHOP = Shop(UUID("11111111-1111-1111-1111-111111111111"), "Sen Spa")
COURSE = Course(
    UUID("22222222-2222-2222-2222-222222222222"),
    "Massage thư giãn",
    60,
    Decimal("500000"),
)
CUSTOMER = Customer("0901234567", "An")
BOOKING_ID = UUID("33333333-3333-3333-3333-333333333333")
CHILD_ID = UUID("44444444-4444-4444-4444-444444444444")


def result(
    template: str | None,
    state: BookingState,
    status: DialogTurnStatus = DialogTurnStatus.SUCCESS,
) -> DialogTurnResult:
    return DialogTurnResult(
        status=status,
        initial_state=BookingState.IDLE,
        final_state=state,
        intent="integration_test",
        instruction_template=template,
        executed_actions=(),
        auto_transition_count=0,
    )


def complete_context(state: BookingState) -> BookingContext:
    return BookingContext(
        conversation_id="conversation-1",
        state=state,
        shop=SHOP,
        main_course=COURSE,
        customer=CUSTOMER,
        booking_date=date(2026, 8, 2),
        start_time=time(10, 30),
        num_customer=1,
        duration_minutes=60,
        phone=CUSTOMER.phone,
        phone_confirmed=True,
        ng_list_checked=True,
    )


def declared_templates(flow: FlowDefinition) -> tuple[str, ...]:
    values: list[str] = []
    for state in flow.states.values():
        if state.on_enter.instruction_template is not None:
            values.append(state.on_enter.instruction_template)
        values.extend(
            failure.instruction_template
            for failure in state.on_enter.on_fail
            if failure.instruction_template is not None
        )
        for transition in state.transitions:
            values.extend(
                failure.instruction_template
                for failure in transition.on_fail
                if failure.instruction_template is not None
            )
        for auto_transition in state.auto_transitions:
            values.extend(
                failure.instruction_template
                for failure in auto_transition.on_fail
                if failure.instruction_template is not None
            )
    return tuple(dict.fromkeys(values))


def test_real_flow_template_audit_has_no_missing_or_unused_renderer() -> None:
    flow = FlowLoader.load(FLOW_PATH)
    builder = InstructionBuilder()
    rules = FlowLoader.load_change_handlers(CHANGE_HANDLERS_PATH)
    declared = (
        declared_templates(flow)
        + tuple(rule.prompt_template for rule in rules.values())
        + ("change_invalid",)
    )

    assert len(declared) == 41
    assert builder.find_missing_templates(declared) == ()
    assert set(builder.registered_templates()) - set(declared) == set()


def test_real_confirmation_template_renders_complete_context() -> None:
    flow = FlowLoader.load(FLOW_PATH)
    template = flow.states[BookingState.AWAITING_CONFIRMATION].on_enter.instruction_template
    context = complete_context(BookingState.AWAITING_CONFIRMATION)

    response = InstructionBuilder().build_response(
        result=result(template, BookingState.AWAITING_CONFIRMATION),
        context=context,
    )

    assert "Sen Spa" in response.text
    assert "02/08/2026" in response.text
    assert "Tên khách hàng: An" in response.text
    assert "Số điện thoại: 0901234567" in response.text


def test_real_group_completed_template_without_code_hides_internal_ids() -> None:
    flow = FlowLoader.load(FLOW_PATH)
    template = flow.states[BookingState.COMPLETED].on_enter.instruction_template
    context = complete_context(BookingState.COMPLETED)
    context.booking = Booking(
        booking_id=BOOKING_ID,
        status="confirmed",
        shop=SHOP,
        main_course=COURSE,
        customer=CUSTOMER,
        booking_date=date(2026, 8, 2),
        start_time=time(10, 30),
        num_customer=2,
    )
    second_child_id = UUID("55555555-5555-5555-5555-555555555555")

    response = InstructionBuilder().build_response(
        result=result(template, BookingState.COMPLETED),
        context=context,
    )

    assert response.status is DialogTurnStatus.SUCCESS
    assert response.metadata == {"booking_created": True}
    assert "Đặt lịch thành công" in response.text
    assert "đã được ghi nhận" in response.text
    assert "Mã đặt lịch" not in response.text
    assert "Tên khách hàng: An" in response.text
    assert "Số điện thoại: 0901234567" in response.text
    assert str(BOOKING_ID) not in response.text
    assert str(CHILD_ID) not in response.text
    assert str(second_child_id) not in response.text
    assert str(CHILD_ID) not in repr(response.metadata)


def test_slot_failure_instruction_uses_safe_renderer() -> None:
    response = InstructionBuilder().build_response(
        result=result(
            "slot_unavailable",
            BookingState.SELECTING_TIME,
            DialogTurnStatus.FAILURE_HANDLED,
        ),
        context=BookingContext("conversation-1"),
    )

    assert response.text == ("Khung giờ vừa chọn không còn trống. Vui lòng chọn khung giờ khác.")


def test_unhandled_result_uses_safe_fallback_even_with_unknown_template() -> None:
    response = InstructionBuilder().build_response(
        result=result(
            "not_registered",
            BookingState.BOOKING_FAILED,
            DialogTurnStatus.FAILURE_UNHANDLED,
        ),
        context=BookingContext("conversation-1"),
    )

    assert response.text == "Đã có lỗi xảy ra. Vui lòng thử lại hoặc liên hệ cửa hàng."
