"""Expose the non-streaming chat endpoint and its transport orchestration."""

from collections.abc import Mapping
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.dependencies import (
    ApplicationContainer,
    InvalidCachedContextError,
    InvalidConversationContextError,
    InvalidConversationIdError,
)
from app.dialog.dialog_controller import DialogTurnStatus
from app.dialog.entity_resolution import (
    EntityResolutionResult,
    EntityResolutionStatus,
    entity_resolution_to_dialog_turn_input,
)
from app.dialog.instruction_builder import DialogResponse
from app.dialog.nlu import (
    NLUEntityKind,
    NLUResolutionStatus,
    to_dialog_turn_input,
)
from app.domain.booking_context import BookingContext
from app.domain.booking_state import BookingState
from app.transport.schemas import ChatRequest, ChatResponse

router = APIRouter(prefix="/api/v1")

_SAFE_METADATA_KEYS = frozenset(
    {
        "available_slot_count",
        "has_addons",
        "booking_created",
        "can_retry",
        "can_change_info",
    }
)
_UNRESOLVED_TEXT = {
    BookingState.IDLE: "Tôi chưa hiểu yêu cầu. Bạn có thể nói: Tôi muốn đặt lịch.",
    BookingState.SELECTING_SHOP: (
        "Vui lòng cho biết cửa hàng hoặc khu vực bạn muốn đặt."
    ),
    BookingState.SELECTING_DATE: (
        "Vui lòng nhập ngày, ví dụ: ngày mai hoặc 15/08."
    ),
    BookingState.SELECTING_PEOPLE: "Vui lòng cho biết số người từ 1 đến 3.",
    BookingState.SELECTING_DURATION: "Vui lòng nhập thời lượng, ví dụ: 60 phút.",
    BookingState.SELECTING_SERVICE: "Vui lòng nhập tên liệu trình bạn muốn chọn.",
    BookingState.SELECTING_TIME: (
        "Vui lòng nhập giờ rõ ràng, ví dụ: 19:00 hoặc 7 giờ tối."
    ),
    BookingState.SELECTING_THERAPIST: (
        "Bạn có thể chọn Nam, Nữ hoặc Không yêu cầu."
    ),
    BookingState.COLLECTING_PHONE: "Vui lòng nhập số điện thoại hợp lệ.",
}
_AMBIGUOUS_TEXT = {
    NLUEntityKind.SHOP: (
        "Đã tìm thấy nhiều cửa hàng phù hợp. Vui lòng chọn một cửa hàng."
    ),
    NLUEntityKind.COURSE: (
        "Đã tìm thấy nhiều liệu trình phù hợp. Vui lòng chọn một liệu trình."
    ),
    NLUEntityKind.THERAPIST: (
        "Đã tìm thấy nhiều kỹ thuật viên phù hợp. "
        "Vui lòng chọn một kỹ thuật viên."
    ),
}
_NOT_FOUND_TEXT = {
    NLUEntityKind.SHOP: (
        "Không tìm thấy cửa hàng phù hợp. Vui lòng nhập lại tên hoặc khu vực."
    ),
    NLUEntityKind.COURSE: (
        "Không tìm thấy liệu trình phù hợp. Vui lòng nhập lại tên liệu trình."
    ),
    NLUEntityKind.THERAPIST: "Không tìm thấy kỹ thuật viên phù hợp.",
}
_UNSUPPORTED_TEXT = {
    NLUEntityKind.SHOP: "Hiện tại hệ thống chưa hỗ trợ tra cứu cửa hàng này.",
    NLUEntityKind.COURSE: "Hiện tại hệ thống chưa hỗ trợ tra cứu liệu trình này.",
    NLUEntityKind.THERAPIST: (
        "Hiện tại hệ thống chưa hỗ trợ tìm kỹ thuật viên theo tên. "
        "Bạn có thể chọn Nam, Nữ hoặc Không yêu cầu."
    ),
}
_ENTITY_FAILURE_TEXT = "Hệ thống chưa thể tra cứu thông tin lúc này. Vui lòng thử lại."
_DEFAULT_UNRESOLVED_TEXT = "Tôi chưa hiểu yêu cầu. Vui lòng nhập lại rõ hơn."


def get_application_container(request: Request) -> ApplicationContainer:
    """Return the single container created by the FastAPI lifespan."""
    container = getattr(request.app.state, "application_container", None)
    if not isinstance(container, ApplicationContainer):
        raise RuntimeError("Application container is unavailable.")
    return container


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    container: Annotated[
        ApplicationContainer,
        Depends(get_application_container),
    ],
) -> ChatResponse:
    """Process one deterministic, non-streaming chat message."""
    try:
        response = await _process_chat_message(request=request, container=container)
    except InvalidConversationIdError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Invalid conversation ID.",
        ) from error
    except (InvalidCachedContextError, InvalidConversationContextError) as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error.",
        ) from error
    return _to_chat_response(request.conversation_id, response)


async def _process_chat_message(
    *,
    request: ChatRequest,
    container: ApplicationContainer,
) -> DialogResponse:
    """Run the deterministic message pipeline without booking business rules."""
    context = await container.conversation_context_store.get_or_create(
        request.conversation_id
    )
    nlu_result = container.deterministic_nlu.parse(
        text=request.message,
        state=context.state,
    )

    if nlu_result.resolution_status is NLUResolutionStatus.UNRESOLVED:
        return _handled_response(
            context,
            _UNRESOLVED_TEXT.get(context.state, _DEFAULT_UNRESOLVED_TEXT),
        )

    if (
        nlu_result.resolution_status
        is NLUResolutionStatus.ENTITY_RESOLUTION_REQUIRED
    ):
        resolution = await container.entity_resolution_coordinator.resolve(
            nlu_result=nlu_result,
            state=context.state,
            context=context,
        )
        if resolution.status is not EntityResolutionStatus.RESOLVED:
            return _entity_response(context, resolution)
        turn = entity_resolution_to_dialog_turn_input(
            resolution,
            state=context.state,
            intent_policy=container.state_intent_policy,
            idempotency_key=request.idempotency_key,
        )
    else:
        turn = to_dialog_turn_input(
            nlu_result,
            state=context.state,
            intent_policy=container.state_intent_policy,
            idempotency_key=request.idempotency_key,
            raw_message=request.message,
        )

    result = await container.dialog_controller.handle_turn(context, turn)
    response = container.instruction_builder.build_response(
        result=result,
        context=context,
    )
    await container.conversation_context_store.save(
        request.conversation_id,
        context,
    )
    return response


def _entity_response(
    context: BookingContext,
    result: EntityResolutionResult,
) -> DialogResponse:
    if result.status is EntityResolutionStatus.AMBIGUOUS:
        return _handled_response(
            context,
            _AMBIGUOUS_TEXT[result.entity_kind],
            _candidate_names(result),
        )
    if result.status is EntityResolutionStatus.NOT_FOUND:
        return _handled_response(context, _NOT_FOUND_TEXT[result.entity_kind])
    if result.status is EntityResolutionStatus.UNSUPPORTED:
        return _handled_response(context, _UNSUPPORTED_TEXT[result.entity_kind])
    return _handled_response(context, _ENTITY_FAILURE_TEXT)


def _candidate_names(result: EntityResolutionResult) -> tuple[str, ...]:
    names: list[str] = []
    seen: set[str] = set()
    for candidate in result.candidates:
        if candidate.display_name not in seen:
            seen.add(candidate.display_name)
            names.append(candidate.display_name)
            if len(names) == 8:
                break
    return tuple(names)


def _handled_response(
    context: BookingContext,
    text: str,
    quick_replies: tuple[str, ...] = (),
) -> DialogResponse:
    return DialogResponse(
        text=text,
        instruction_template=None,
        state=context.state,
        status=DialogTurnStatus.FAILURE_HANDLED,
        quick_replies=quick_replies,
    )


def _to_chat_response(
    conversation_id: str,
    response: DialogResponse,
) -> ChatResponse:
    return ChatResponse(
        conversation_id=conversation_id,
        text=response.text,
        state=response.state.value,
        status=response.status.value,
        instruction_template=response.instruction_template,
        quick_replies=list(response.quick_replies),
        metadata=_safe_metadata(response.metadata),
    )


def _safe_metadata(
    metadata: Mapping[str, object],
) -> dict[str, bool | int | float | str | None]:
    safe: dict[str, bool | int | float | str | None] = {}
    for key, value in metadata.items():
        if key in _SAFE_METADATA_KEYS and (
            value is None or type(value) in {bool, int, float, str}
        ):
            safe[key] = cast(bool | int | float | str | None, value)
    return safe
