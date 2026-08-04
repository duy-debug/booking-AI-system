"""Expose JSON and SSE chat endpoints over one shared orchestration pipeline."""

import logging
import os
from collections.abc import AsyncIterator, Mapping
from dataclasses import fields
from datetime import datetime, timedelta
from time import perf_counter
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from app.application.handlers.check_availability_handler import CheckAvailabilityHandler
from app.application.handlers.search_service_handler import SearchServiceHandler
from app.application.handlers.search_shop_handler import SearchShopHandler
from app.application.ports.booking_gateway import (
    AvailableTherapistRequest,
    TherapistAvailabilityGateway,
)
from app.core.logging import (
    bind_conversation,
    bind_correlation_id,
    bind_turn,
    elapsed_ms,
    reset_conversation,
    reset_correlation_id,
    reset_turn,
    trace_log,
)
from app.dependencies import (
    ApplicationContainer,
    InvalidCachedContextError,
    InvalidConversationContextError,
    InvalidConversationIdError,
)
from app.dialog.dialog_controller import DialogTurnInput, DialogTurnResult, DialogTurnStatus
from app.dialog.entity_resolution import (
    EntityResolutionResult,
    EntityResolutionStatus,
    entity_resolution_to_dialog_turn_input,
)
from app.dialog.instruction_builder import DialogResponse
from app.dialog.nlu import (
    NLUEntityKind,
    NLUResolutionStatus,
    NLUResult,
    to_dialog_turn_input,
)
from app.domain.booking import CourseType, Service, Shop, TherapistPreference
from app.domain.booking_context import BookingContext, ServiceSelectionMode
from app.domain.booking_state import BookingState
from app.transport.schemas import ChatRequest, ChatResponse
from app.transport.sse import SSEEventType, encode_sse_event

router = APIRouter(prefix="/api/v1")
logger = logging.getLogger(__name__)

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
    }
)
_UNRESOLVED_TEXT = {
    BookingState.IDLE: "Tôi chưa hiểu yêu cầu. Bạn có thể nói: Tôi muốn đặt lịch.",
    BookingState.SELECTING_SHOP: ("Vui lòng cho biết cửa hàng hoặc khu vực bạn muốn đặt."),
    BookingState.SELECTING_DATE: ("Vui lòng nhập ngày, ví dụ: ngày mai hoặc 15/08."),
    BookingState.SELECTING_PEOPLE: "Vui lòng cho biết số người từ 1 đến 3.",
    BookingState.SELECTING_DURATION: "Vui lòng nhập thời lượng, ví dụ: 60 phút.",
    BookingState.SELECTING_SERVICE: "Vui lòng nhập tên liệu trình bạn muốn chọn.",
    BookingState.SELECTING_TIME: ("Vui lòng nhập giờ rõ ràng, ví dụ: 19:00 hoặc 7 giờ tối."),
    BookingState.SELECTING_THERAPIST: ("Bạn có thể chọn Nam, Nữ hoặc Không yêu cầu."),
    BookingState.COLLECTING_PHONE: "Vui lòng nhập số điện thoại hợp lệ.",
    BookingState.COLLECTING_NAME: "Vui lòng nhập tên khách hàng.",
}
_AMBIGUOUS_TEXT = {
    NLUEntityKind.SHOP: ("Đã tìm thấy nhiều cửa hàng phù hợp. Vui lòng chọn một cửa hàng."),
    NLUEntityKind.COURSE: ("Đã tìm thấy nhiều liệu trình phù hợp. Vui lòng chọn một liệu trình."),
    NLUEntityKind.THERAPIST: (
        "Đã tìm thấy nhiều kỹ thuật viên phù hợp. Vui lòng chọn một kỹ thuật viên."
    ),
}
_NOT_FOUND_TEXT = {
    NLUEntityKind.SHOP: ("Không tìm thấy cửa hàng phù hợp. Vui lòng nhập lại tên hoặc khu vực."),
    NLUEntityKind.COURSE: ("Không tìm thấy liệu trình phù hợp. Vui lòng nhập lại tên liệu trình."),
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
_RECOVERY_QUICK_REPLIES = {
    BookingState.IDLE: ("Tôi muốn đặt lịch", "Xem danh sách cửa hàng"),
    BookingState.SELECTING_DATE: ("Hôm nay", "Ngày mai"),
    BookingState.SELECTING_PEOPLE: ("1 người", "2 người", "3 người"),
    BookingState.SELECTING_DURATION: ("45 phút", "60 phút", "90 phút"),
    BookingState.SELECTING_THERAPIST: ("Không yêu cầu", "Nam", "Nữ"),
    BookingState.VERIFYING_PHONE: ("Xác nhận", "Nhập lại"),
    BookingState.AWAITING_CONFIRMATION: ("Xác nhận", "Chỉnh sửa", "Hủy"),
    BookingState.BOOKING_FAILED: ("Thử lại", "Chọn giờ khác", "Hủy"),
}
_TERMINAL_CHANGE_TEXT = (
    "Đặt lịch này đã hoàn tất. Vui lòng tạo yêu cầu mới để thay đổi hoặc hủy lịch."
)


def get_application_container(request: Request) -> ApplicationContainer:
    """Return the single container created by the FastAPI lifespan."""
    container = getattr(request.app.state, "application_container", None)
    if not isinstance(container, ApplicationContainer):
        raise RuntimeError("Application container is unavailable.")
    return container


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    http_request: Request,
    container: Annotated[
        ApplicationContainer,
        Depends(get_application_container),
    ],
) -> ChatResponse:
    """Process one deterministic, non-streaming chat message."""
    try:
        response = await _process_chat_message(
            request=request,
            container=container,
            correlation_id=http_request.headers.get("x-correlation-id"),
        )
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


@router.post("/chat/stream", response_class=StreamingResponse)
async def chat_stream(
    request: ChatRequest,
    http_request: Request,
    container: Annotated[
        ApplicationContainer,
        Depends(get_application_container),
    ],
) -> StreamingResponse:
    """Stream one deterministic response as business-level SSE events."""
    return StreamingResponse(
        _stream_chat_events(
            request=request,
            container=container,
            correlation_id=http_request.headers.get("x-correlation-id"),
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


async def _stream_chat_events(
    *,
    request: ChatRequest,
    container: ApplicationContainer,
    correlation_id: str | None = None,
) -> AsyncIterator[str]:
    """Yield started, response and terminal events for one shared chat pipeline."""
    yield encode_sse_event(
        event=SSEEventType.STARTED,
        data={"conversation_id": request.conversation_id},
    )

    try:
        if correlation_id is None:
            dialog_response = await _process_chat_message(
                request=request,
                container=container,
            )
        else:
            dialog_response = await _process_chat_message(
                request=request,
                container=container,
                correlation_id=correlation_id,
            )
        response = _to_chat_response(request.conversation_id, dialog_response)
        message_event = encode_sse_event(
            event=SSEEventType.MESSAGE,
            data=response.model_dump(mode="json"),
        )
        completed_event = encode_sse_event(
            event=SSEEventType.COMPLETED,
            data={
                "conversation_id": request.conversation_id,
                "stream_status": "completed",
                "dialog_status": response.status,
            },
        )
    except Exception:
        yield encode_sse_event(
            event=SSEEventType.ERROR,
            data={
                "conversation_id": request.conversation_id,
                "code": "chat_processing_failed",
                "message": "Hệ thống chưa thể xử lý yêu cầu lúc này.",
            },
        )
        return

    yield message_event
    yield completed_event


async def _process_chat_message(
    *,
    request: ChatRequest,
    container: ApplicationContainer,
    correlation_id: str | None = None,
) -> DialogResponse:
    """Run the deterministic message pipeline without booking business rules."""
    token = bind_conversation(request.conversation_id)
    correlation_token = bind_correlation_id(correlation_id)
    started_at = perf_counter()
    context = await container.conversation_context_store.get_or_create(request.conversation_id)
    turn_token = bind_turn(context.begin_turn())
    context_before = _context_snapshot(context)
    initial_state = context.state
    trace_log(logger, logging.INFO, "Turn", "started", state=initial_state.value)
    if _local_debug_enabled("LOG_RAW_CHAT_MESSAGES"):
        trace_log(
            logger,
            logging.DEBUG,
            "Turn",
            "user_message",
            function="_process_chat_message",
            user_message=request.message[:500],
        )
    try:
        response = await _process_bound_chat_message(
            request=request,
            container=container,
            context=context,
        )
        _log_instruction(response)
        _trace_context_diff(context_before, context)
        trace_log(
            logger,
            logging.INFO,
            "Response",
            "prepared",
            state=response.state.value,
            status=response.status.value,
            quick_reply_count=len(response.quick_replies),
            instruction_template=response.instruction_template or "none",
        )
        if _local_debug_enabled("LOG_RAW_CHAT_RESPONSES"):
            trace_log(
                logger,
                logging.DEBUG,
                "Response",
                "assistant_message",
                function="_process_chat_message",
                assistant_message=response.text[:1000],
            )
        trace_log(
            logger,
            logging.INFO,
            "Turn",
            "completed",
            state=response.state.value,
            status=response.status.value,
            duration_ms=elapsed_ms(started_at),
        )
        return response
    except Exception as error:
        trace_log(
            logger,
            logging.ERROR,
            "Turn",
            "failed",
            state=context.state.value,
            exception_type=type(error).__name__,
            duration_ms=elapsed_ms(started_at),
        )
        raise
    finally:
        reset_turn(turn_token)
        reset_correlation_id(correlation_token)
        reset_conversation(token)


async def _process_bound_chat_message(
    *,
    request: ChatRequest,
    container: ApplicationContainer,
    context: BookingContext,
) -> DialogResponse:
    """Process a turn after its safe logging context has been bound."""
    if (
        context.state is BookingState.AWAITING_CONFIRMATION
        and _is_generic_change_request(request.message)
    ):
        return _change_menu_response(context)

    nlu_result = container.deterministic_nlu.parse(
        text=request.message,
        state=context.state,
    )
    resolver = "deterministic"
    used_llm_fallback = False

    if context.state in {
        BookingState.COMPLETED,
        BookingState.CANCELLED,
    } and nlu_result.matched_rule in {"change_booking_field", "change_entity_query"}:
        return _handled_response(context, _TERMINAL_CHANGE_TEXT)

    if nlu_result.resolution_status is NLUResolutionStatus.UNRESOLVED:
        nlu_result = await container.llm_nlu_fallback.parse(
            text=request.message,
            state=context.state,
        )
        resolver = "llm"
        used_llm_fallback = True

    trace_log(
        logger,
        logging.INFO,
        "NLU",
        "resolved",
        intent=nlu_result.intent or "unresolved",
        resolver=resolver,
        entity=nlu_result.entity_kind.value if nlu_result.entity_kind else "none",
        function="parse",
        input_summary=f"state={context.state.value}, chars={len(request.message)}",
        output_summary=(
            f"status={nlu_result.resolution_status.value}, rule={nlu_result.matched_rule or 'none'}"
        ),
        status=nlu_result.resolution_status.value,
    )

    if nlu_result.intent in {"greeting", "thanks", "ask_why", "repeat_last_question"}:
        _trace_route("global_intent", "global_intent", nlu_result, context)
        if (
            nlu_result.intent == "repeat_last_question"
            and context.last_failure_code in {"slot_api_error", "no_slots_available"}
        ):
            return await _retry_availability(container=container, context=context)
        return _global_intent_response(nlu_result.intent, context)

    if nlu_result.intent == "restart_booking":
        _trace_route("restart", "deterministic_match", nlu_result, context)
        context.reset()
        context.state = BookingState.SELECTING_SHOP
        response = _global_intent_response("restart_booking", context)
        response = await _with_proactive_suggestions(
            response=response,
            container=container,
            context=context,
        )
        await container.conversation_context_store.save(request.conversation_id, context)
        _trace_context_saved(context)
        return response

    if nlu_result.intent in _DISCOVERY_INTENTS:
        _trace_route("discovery", "deterministic_match", nlu_result, context)
        response = await _handle_discovery(
            nlu_result=nlu_result,
            container=container,
            context=context,
        )
        await container.conversation_context_store.save(
            request.conversation_id,
            context,
        )
        _trace_context_saved(context)
        return response

    if nlu_result.intent == "ask_question":
        _trace_route(
            "faq",
            "llm_fallback" if used_llm_fallback else "deterministic_match",
            nlu_result,
            context,
        )
        faq_turn = to_dialog_turn_input(
            nlu_result,
            state=context.state,
            intent_policy=container.state_intent_policy,
            raw_message=request.message,
        )
        query = faq_turn.payload["query"]
        assert isinstance(query, str)
        knowledge_started = perf_counter()
        response = await container.faq_manager.answer(
            query=query,
            context=context,
        )
        trace_log(
            logger,
            logging.INFO,
            "Knowledge",
            "completed",
            status=response.status.value,
            source_count=response.metadata.get("source_count", 0),
            duration_ms=elapsed_ms(knowledge_started),
        )
        return response

    if nlu_result.resolution_status is NLUResolutionStatus.UNRESOLVED:
        _trace_route("unresolved_recovery", "unresolved_recovery", nlu_result, context)
        return _handled_response(
            context,
            _UNRESOLVED_TEXT.get(context.state, _DEFAULT_UNRESOLVED_TEXT),
            _state_recovery_quick_replies(context),
        )

    if nlu_result.resolution_status is NLUResolutionStatus.ENTITY_RESOLUTION_REQUIRED:
        _trace_route("entity_resolution", "state_expected_entity", nlu_result, context)
        entity_kind = nlu_result.entity_kind
        assert entity_kind is not None
        resolution_started = perf_counter()
        resolution = await container.entity_resolution_coordinator.resolve(
            nlu_result=nlu_result,
            state=context.state,
            context=context,
        )
        trace_log(
            logger,
            logging.INFO,
            "EntityResolver",
            "completed",
            entity=resolution.entity_kind.value,
            resolution_status=resolution.status.value,
            candidate_count=len(resolution.candidates),
            function="resolve",
            input_summary=f"state={context.state.value}, entity={entity_kind.value}",
            output_summary=f"matched={_matched_display_name(resolution)}",
            search_scope=context.state.value,
            error_code=resolution.failure_code or "none",
            duration_ms=elapsed_ms(resolution_started),
        )
        if _local_debug_enabled("LOG_RAW_CHAT_MESSAGES"):
            trace_log(
                logger,
                logging.DEBUG,
                "EntityResolver",
                "query",
                function="resolve",
                query=request.message[:500],
                entity_type=entity_kind.value,
                search_scope=context.state.value,
            )
        if resolution.status is not EntityResolutionStatus.RESOLVED:
            return await _entity_response(context, resolution, container)
        turn = entity_resolution_to_dialog_turn_input(
            resolution,
            state=context.state,
            intent_policy=container.state_intent_policy,
            idempotency_key=request.idempotency_key,
        )
    else:
        _trace_route(
            "dialog",
            "llm_fallback" if used_llm_fallback else "deterministic_match",
            nlu_result,
            context,
        )
        turn = to_dialog_turn_input(
            nlu_result,
            state=context.state,
            intent_policy=container.state_intent_policy,
            idempotency_key=request.idempotency_key,
            raw_message=request.message,
        )

    trace_log(
        logger,
        logging.INFO,
        "DialogCtrl",
        "dispatch",
        intent=turn.intent,
        state=context.state.value,
    )
    controller_started = perf_counter()
    result = await container.dialog_controller.handle_turn(context, turn)
    result = await _consume_requested_entities(
        container=container,
        context=context,
        result=result,
        idempotency_key=request.idempotency_key,
    )
    trace_log(
        logger,
        logging.INFO,
        "DialogCtrl",
        "transition",
        from_state=result.initial_state.value,
        to_state=result.final_state.value,
        intent=result.intent,
        status=result.status.value,
        function="handle_turn",
        input_summary=(
            f"intent={turn.intent}, "
            f"payload_keys={','.join(sorted(turn.payload)) or 'none'}"
        ),
        output_summary=f"actions={','.join(result.executed_actions) or 'none'}",
        error_code=result.failure_code or "none",
        duration_ms=elapsed_ms(controller_started),
    )
    trace_log(
        logger,
        logging.INFO,
        "StateMachine",
        "transition",
        from_state=result.initial_state.value,
        to_state=result.final_state.value,
    )
    if result.executed_actions:
        trace_log(
            logger,
            logging.INFO,
            "ToolBridge",
            "completed",
            function="execute_actions",
            input_summary=f"action_count={len(result.executed_actions)}",
            output_summary=",".join(result.executed_actions),
            status=result.status.value,
        )
    if result.failure_code is not None:
        trace_log(
            logger,
            logging.WARNING,
            "DialogCtrl",
            "business_failure",
            error_code=result.failure_code,
            failed_action=result.failed_action or "none",
        )
    response = container.instruction_builder.build_response(
        result=result,
        context=context,
    )
    if result.status is DialogTurnStatus.SUCCESS:
        response = await _with_proactive_suggestions(
            response=response,
            container=container,
            context=context,
        )
    elif not response.quick_replies:
        response = _with_state_recovery_suggestions(response, context)
    if not (result.intent == "change_info" and result.status is not DialogTurnStatus.SUCCESS):
        await container.conversation_context_store.save(
            request.conversation_id,
            context,
        )
        _trace_context_saved(context)
    return response


async def _consume_requested_entities(
    *,
    container: ApplicationContainer,
    context: BookingContext,
    result: DialogTurnResult,
    idempotency_key: str | None,
) -> DialogTurnResult:
    """Apply previously extracted fields only when their workflow step is reached."""
    follow_up: DialogTurnInput | None = None
    if (
        result.status is DialogTurnStatus.SUCCESS
        and context.state is BookingState.SELECTING_DATE
        and context.requested_booking_date is not None
    ):
        booking_date = context.requested_booking_date
        context.requested_booking_date = None
        follow_up = DialogTurnInput(
            "select_date",
            {"booking_date": booking_date},
            idempotency_key=idempotency_key,
        )
    elif (
        result.status is DialogTurnStatus.SUCCESS
        and context.state is BookingState.SELECTING_TIME
        and context.requested_start_time is not None
    ):
        start_time = context.requested_start_time
        context.requested_start_time = None
        follow_up = DialogTurnInput(
            "select_time",
            {"start_time": start_time},
            idempotency_key=idempotency_key,
        )
    if follow_up is None:
        return result
    consumed = await container.dialog_controller.handle_turn(context, follow_up)
    trace_log(
        logger,
        logging.INFO,
        "DialogCtrl",
        "prefilled_entity_consumed",
        intent=follow_up.intent,
        from_state=consumed.initial_state.value,
        to_state=consumed.final_state.value,
        status=consumed.status.value,
    )
    return consumed


def _trace_route(
    route: str,
    reason: str,
    result: NLUResult,
    context: BookingContext,
) -> None:
    trace_log(
        logger,
        logging.INFO,
        "Router",
        "dispatch",
        route=route,
        reason=reason,
        intent=result.intent or "unresolved",
        state=context.state.value,
    )


def _context_snapshot(context: BookingContext) -> dict[str, object]:
    return {
        item.name: getattr(context, item.name)
        for item in fields(context)
        if item.name not in {"conversation_id", "turn_sequence"}
    }


def _trace_context_diff(before: Mapping[str, object], context: BookingContext) -> None:
    after = _context_snapshot(context)
    changed = sorted(name for name, value in after.items() if value != before[name])
    cleared = sorted(
        name for name in changed if before[name] is not None and after[name] is None
    )
    preserved = sorted(
        name
        for name, value in after.items()
        if _is_meaningful_context_value(value) and value == before[name]
    )
    trace_log(
        logger,
        logging.INFO,
        "DialogCtrl",
        "context_diff",
        function="handle_turn",
        fields_changed=changed,
        fields_preserved=preserved,
        fields_cleared=cleared,
        status="changed" if changed else "unchanged",
    )


def _is_meaningful_context_value(value: object) -> bool:
    return value is not None and value is not False and value != () and value != "none"


def _matched_display_name(resolution: EntityResolutionResult) -> str:
    for value in resolution.dispatch_payload.values():
        display_name = getattr(value, "name", None)
        if isinstance(display_name, str):
            return display_name
    return "none"


def _trace_context_saved(context: BookingContext) -> None:
    trace_log(
        logger,
        logging.DEBUG,
        "Context",
        "saved",
        state=context.state.value,
    )


async def _with_proactive_suggestions(
    *,
    response: DialogResponse,
    container: ApplicationContainer,
    context: BookingContext,
) -> DialogResponse:
    """Load safe choices for the state the customer has just entered."""
    try:
        if context.state is BookingState.SELECTING_SHOP:
            shops = list(context.suggested_shops)
            if not context.suggested_shops_loaded:
                shop_handler = cast(SearchShopHandler, container.handler(SearchShopHandler))
                shops = await shop_handler.execute()
            return _shop_catalog_response(context, shops, filtered=False)

        if context.state is BookingState.SELECTING_SERVICE and context.shop is not None:
            course_type = (
                CourseType.ADDON
                if context.service_selection_mode is ServiceSelectionMode.ADDON
                else CourseType.MAIN
            )
            service_handler = cast(
                SearchServiceHandler,
                container.handler(SearchServiceHandler),
            )
            services = await service_handler.execute(
                context.shop.shop_id,
                course_type=course_type,
            )
            if course_type is CourseType.MAIN and context.duration_minutes is not None:
                services = [
                    service
                    for service in services
                    if service.duration_minutes == context.duration_minutes
                ]
            return _service_step_response(
                context,
                services,
                course_type=course_type,
            )

        if context.state is BookingState.SELECTING_THERAPIST and context.num_customer == 1:
            therapists = await _available_therapists(container, context)
            names = tuple(
                item.therapist_name
                for item in therapists[:8]
                if item.therapist_name is not None
            )
            if names:
                return DialogResponse(
                    text=(
                        "Kỹ thuật viên đang phù hợp với khung giờ đã chọn:\n"
                        + "\n".join(f"{index}. {name}" for index, name in enumerate(names, 1))
                        + "\nBạn có thể chọn theo tên, giới tính hoặc không yêu cầu."
                    ),
                    instruction_template=response.instruction_template,
                    state=context.state,
                    status=response.status,
                    quick_replies=names + ("Không yêu cầu", "Nam", "Nữ"),
                    metadata=response.metadata,
                )
    except Exception as error:
        trace_log(
            logger,
            logging.WARNING,
            "Handler",
            "suggestions_failed",
            state=context.state.value,
            error_code=type(error).__name__,
        )
    return response


async def _available_therapists(
    container: ApplicationContainer,
    context: BookingContext,
) -> list[TherapistPreference]:
    if (
        context.shop is None
        or context.booking_date is None
        or context.start_time is None
        or context.total_duration_minutes is None
    ):
        return []
    end_time = (
        datetime.combine(context.booking_date, context.start_time)
        + timedelta(minutes=context.total_duration_minutes)
    ).time()
    gateway = cast(TherapistAvailabilityGateway, container.booking_gateway)
    return await gateway.search_available_therapists(
        AvailableTherapistRequest(
            shop_id=context.shop.shop_id,
            booking_date=context.booking_date,
            start_time=context.start_time,
            end_time=end_time,
        )
    )


def _log_instruction(response: DialogResponse) -> None:
    trace_log(
        logger,
        logging.INFO,
        "DialogCtrl",
        "instruction",
        instruction_template=response.instruction_template or "none",
        instruction_length=len(response.text),
    )
    if _local_debug_enabled("LOG_FULL_INSTRUCTIONS"):
        trace_log(
            logger,
            logging.DEBUG,
            "DialogCtrl",
            "instruction_content",
            instruction=response.text,
        )


def _local_debug_enabled(name: str) -> bool:
    environment = os.getenv("ENVIRONMENT", "production").strip().casefold()
    enabled = os.getenv(name, "false").strip().casefold()
    return environment in {"local", "development", "dev"} and enabled in {
        "true",
        "1",
        "yes",
        "on",
    }


_DISCOVERY_INTENTS = frozenset(
    {
        "list_shops",
        "search_shops",
        "list_services",
        "list_addons",
        "list_available_times",
        "list_therapists",
    }
)


async def _handle_discovery(
    *,
    nlu_result: NLUResult,
    container: ApplicationContainer,
    context: BookingContext,
) -> DialogResponse:
    """Run one read-only catalog operation without selecting an entity."""
    try:
        if nlu_result.intent in {"list_shops", "search_shops"}:
            query = nlu_result.payload.get("location_query")
            if query is not None and not isinstance(query, str):
                return _handled_response(context, "Vui lòng nhập lại khu vực cần tìm.")
            shop_handler = cast(SearchShopHandler, container.handler(SearchShopHandler))
            shops = await shop_handler.execute(query)
            if shops and context.state is BookingState.IDLE:
                context.state = BookingState.SELECTING_SHOP
            return _shop_catalog_response(context, shops, filtered=query is not None)

        if nlu_result.intent in {"list_services", "list_addons"}:
            if context.shop is None:
                return _handled_response(
                    context,
                    "Bạn hãy chọn cửa hàng trước để tôi tải danh sách liệu trình từ POS.",
                )
            course_type = (
                CourseType.ADDON
                if nlu_result.intent == "list_addons"
                else CourseType.MAIN
            )
            service_handler = cast(
                SearchServiceHandler,
                container.handler(SearchServiceHandler),
            )
            services = await service_handler.execute(
                context.shop.shop_id,
                course_type=course_type,
            )
            if context.duration_minutes is not None:
                services = [
                    service
                    for service in services
                    if course_type is CourseType.ADDON
                    or service.duration_minutes == context.duration_minutes
                ]
            return _service_catalog_response(context, services)

        if nlu_result.intent == "list_available_times":
            missing = _missing_availability_field(context)
            if missing is not None:
                return _handled_response(context, missing)
            availability_handler = cast(
                CheckAvailabilityHandler,
                container.handler(CheckAvailabilityHandler),
            )
            slots = await availability_handler.execute(context)
            context.state = BookingState.SELECTING_TIME
            context.last_failure_code = None
            labels = tuple(slot.strftime("%H:%M") for slot in slots)
            return _catalog_response(
                context,
                "Các khung giờ đang trống: " + ", ".join(labels) + ". Bạn muốn chọn giờ nào?",
                labels,
                len(labels),
            )

        if nlu_result.intent == "list_therapists":
            if context.num_customer is not None and context.num_customer >= 2:
                return _handled_response(
                    context,
                    "Đặt lịch nhóm không hỗ trợ chọn kỹ thuật viên cá nhân.",
                )
            return _handled_response(
                context,
                "POS hiện chưa cung cấp API danh sách kỹ thuật viên cho chatbot.",
            )
    except Exception as error:
        trace_log(
            logger,
            logging.WARNING,
            "Handler",
            "discovery_failed",
            action=nlu_result.intent or "unknown",
            error_code=type(error).__name__,
        )
        context.last_failure_code = type(error).__name__
        return _handled_response(
            context,
            "Hệ thống chưa thể tải danh sách từ POS lúc này. Vui lòng thử lại.",
        )
    return _handled_response(context, "Yêu cầu danh sách chưa được hỗ trợ.")


def _shop_catalog_response(
    context: BookingContext,
    shops: list[Shop],
    *,
    filtered: bool,
) -> DialogResponse:
    if not shops:
        message = (
            "Không tìm thấy cửa hàng trong khu vực này. Vui lòng thử tên khu vực khác."
            if filtered
            else "POS hiện không trả về cửa hàng nào."
        )
        return _handled_response(context, message)
    names = tuple(shop.name for shop in shops)
    visible = names[:8]
    lines = "\n".join(f"{index}. {name}" for index, name in enumerate(visible, 1))
    suffix = (
        f"\nĐang hiển thị 8/{len(names)} kết quả; bạn có thể nhập tên hoặc khu vực."
        if len(names) > 8
        else ""
    )
    text = f"Komorebi hiện có các cửa hàng:\n{lines}{suffix}\nBạn muốn chọn cửa hàng nào?"
    return _catalog_response(context, text, visible, len(names))


def _service_catalog_response(
    context: BookingContext,
    services: list[Service],
) -> DialogResponse:
    if not services:
        return _handled_response(
            context,
            "POS không trả về liệu trình phù hợp với cửa hàng và thời lượng hiện tại.",
        )
    main = [item for item in services if item.course_type is CourseType.MAIN]
    addons = [item for item in services if item.course_type is CourseType.ADDON]
    sections: list[str] = []
    if main:
        sections.append("Liệu trình chính:\n" + _numbered_service_names(main))
    if addons:
        sections.append("Add-on:\n" + _numbered_service_names(addons))
    names = tuple(item.name for item in services[:8])
    text = "\n".join(sections) + "\nBạn muốn chọn liệu trình nào?"
    return _catalog_response(context, text, names, len(services))


def _service_step_response(
    context: BookingContext,
    services: list[Service],
    *,
    course_type: CourseType,
) -> DialogResponse:
    if course_type is CourseType.MAIN:
        if not services:
            return _handled_response(
                context,
                "POS không có liệu trình chính phù hợp với thời lượng đã chọn.",
            )
        visible = services[:8]
        text = (
            "Các liệu trình chính phù hợp:\n"
            + _numbered_service_names(visible)
            + "\nBạn hãy chọn một liệu trình chính."
        )
        return _catalog_response(
            context,
            text,
            tuple(service.name for service in visible),
            len(services),
        )

    if context.service is None:
        raise ValueError("An add-on suggestion requires a selected main course.")
    visible = services[:7]
    if visible:
        text = (
            f"Liệu trình chính đã chọn: {context.service.name}.\n"
            "Các add-on có thể chọn thêm:\n"
            + _numbered_service_names(visible)
            + "\nBạn hãy chọn một add-on hoặc bỏ qua bước này."
        )
    else:
        text = (
            f"Liệu trình chính đã chọn: {context.service.name}. "
            "Cửa hàng hiện không có add-on khả dụng; bạn có thể tiếp tục chọn giờ."
        )
    return _catalog_response(
        context,
        text,
        tuple(service.name for service in visible) + ("Không chọn add-on",),
        len(services),
    )


def _numbered_service_names(services: list[Service]) -> str:
    return "\n".join(
        f"{index}. {service.name}" for index, service in enumerate(services[:8], 1)
    )


def _catalog_response(
    context: BookingContext,
    text: str,
    quick_replies: tuple[str, ...],
    item_count: int,
) -> DialogResponse:
    return DialogResponse(
        text=text,
        instruction_template=None,
        state=context.state,
        status=DialogTurnStatus.SUCCESS,
        quick_replies=quick_replies,
        metadata={"item_count": item_count},
    )


def _missing_availability_field(context: BookingContext) -> str | None:
    fields = (
        (context.shop, "Bạn hãy chọn cửa hàng trước khi xem giờ trống."),
        (context.booking_date, "Bạn hãy chọn ngày trước khi xem giờ trống."),
        (context.num_customer, "Bạn hãy chọn số người trước khi xem giờ trống."),
        (context.duration_minutes, "Bạn hãy chọn thời lượng trước khi xem giờ trống."),
        (context.service, "Bạn hãy chọn liệu trình trước khi xem giờ trống."),
    )
    return next((message for value, message in fields if value is None), None)


async def _entity_response(
    context: BookingContext,
    result: EntityResolutionResult,
    container: ApplicationContainer,
) -> DialogResponse:
    if result.status is EntityResolutionStatus.AMBIGUOUS:
        return _handled_response(
            context,
            _AMBIGUOUS_TEXT[result.entity_kind],
            _candidate_names(result),
        )
    if result.status is EntityResolutionStatus.NOT_FOUND:
        if result.entity_kind is NLUEntityKind.COURSE and context.shop is not None:
            handler = cast(SearchServiceHandler, container.handler(SearchServiceHandler))
            course_type = (
                CourseType.ADDON
                if context.service_selection_mode is ServiceSelectionMode.ADDON
                else CourseType.MAIN
            )
            services = await handler.execute(context.shop.shop_id, course_type=course_type)
            if course_type is CourseType.MAIN and context.duration_minutes is not None:
                services = [
                    service
                    for service in services
                    if service.duration_minutes == context.duration_minutes
                ]
            if services:
                noun = "add-on" if course_type is CourseType.ADDON else "liệu trình chính"
                visible = services[:8]
                return _handled_response(
                    context,
                    f"Không tìm thấy {noun} phù hợp. Bạn có thể chọn:\n"
                    + _numbered_service_names(visible),
                    tuple(service.name for service in visible),
                )
        return _handled_response(context, _NOT_FOUND_TEXT[result.entity_kind])
    if result.status is EntityResolutionStatus.UNSUPPORTED:
        return _handled_response(context, _UNSUPPORTED_TEXT[result.entity_kind])
    return _handled_response(context, _ENTITY_FAILURE_TEXT)


async def _retry_availability(
    *, container: ApplicationContainer, context: BookingContext
) -> DialogResponse:
    try:
        missing = _missing_availability_field(context)
        if missing is not None:
            return _handled_response(context, missing)
        handler = cast(
            CheckAvailabilityHandler,
            container.handler(CheckAvailabilityHandler),
        )
        slots = await handler.execute(context)
        context.state = BookingState.SELECTING_TIME
        context.last_failure_code = None
        labels = tuple(slot.strftime("%H:%M") for slot in slots)
        return _catalog_response(
            context,
            "Đã tải lại các khung giờ trống: " + ", ".join(labels) + ".",
            labels,
            len(labels),
        )
    except Exception as error:
        context.last_failure_code = type(error).__name__
        return _handled_response(
            context,
            "Tôi vẫn chưa tải được khung giờ từ POS. Các thông tin đã chọn "
            "vẫn được giữ; bạn có thể thử lại hoặc bỏ add-on.",
            ("Thử lại", "Không chọn add-on"),
        )


def _global_intent_response(intent: str, context: BookingContext) -> DialogResponse:
    if intent == "greeting":
        text = "Xin chào! Thông tin đặt lịch hiện tại của bạn vẫn được giữ."
    elif intent == "thanks":
        text = "Rất vui được hỗ trợ bạn."
    elif intent == "restart_booking":
        text = "Mình đã bắt đầu lại. Bạn hãy chọn cửa hàng."
    else:
        prompt = _UNRESOLVED_TEXT.get(context.state, _DEFAULT_UNRESOLVED_TEXT)
        if context.last_failure_code in {"slot_api_error", "no_slots_available"}:
            text = (
                "Hiện tại tôi chưa tải được khung giờ từ POS. Thông tin cửa hàng, ngày, "
                "số người và liệu trình vẫn được giữ. Bạn có thể thử lại hoặc chọn liệu trình khác."
            )
        else:
            text = f"Bước hiện tại: {prompt}"
    return DialogResponse(
        text=text,
        instruction_template=None,
        state=context.state,
        status=DialogTurnStatus.SUCCESS,
    )


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
        quick_replies=quick_replies or _state_recovery_quick_replies(context),
    )


def _with_state_recovery_suggestions(
    response: DialogResponse,
    context: BookingContext,
) -> DialogResponse:
    """Add verified next-step choices without replacing the failure explanation."""
    return DialogResponse(
        text=response.text,
        instruction_template=response.instruction_template,
        state=response.state,
        status=response.status,
        quick_replies=_state_recovery_quick_replies(context),
        metadata=response.metadata,
    )


def _state_recovery_quick_replies(context: BookingContext) -> tuple[str, ...]:
    """Return safe choices derived from the current state and validated context."""
    if context.state is BookingState.SELECTING_SHOP:
        names = tuple(shop.name for shop in context.suggested_shops[:8])
        return names or ("Xem danh sách cửa hàng",)
    if context.state is BookingState.SELECTING_SERVICE:
        if context.service is not None:
            return ("Không chọn add-on", "Xem danh sách add-on")
        return ("Xem danh sách liệu trình",)
    if context.state is BookingState.SELECTING_TIME:
        return tuple(slot.strftime("%H:%M") for slot in (context.available_slots or ()))
    return _RECOVERY_QUICK_REPLIES.get(context.state, ())


def _is_generic_change_request(message: str) -> bool:
    normalized = " ".join(message.casefold().strip().split())
    return normalized in {
        "chỉnh sửa",
        "chỉnh sửa booking",
        "chỉnh sửa đặt lịch",
        "tôi muốn chỉnh sửa",
        "tôi muốn chỉnh sửa booking",
        "sửa thông tin",
        "chỉnh lại thông tin",
        "quay lại sửa",
    }


def _change_menu_response(context: BookingContext) -> DialogResponse:
    return DialogResponse(
        text=(
            "Bạn muốn chỉnh sửa thông tin nào? Việc chỉnh sửa sẽ không tạo booking "
            "cho đến khi bạn xác nhận lại."
        ),
        instruction_template=None,
        state=context.state,
        status=DialogTurnStatus.SUCCESS,
        quick_replies=(
            "Đổi cửa hàng",
            "Đổi ngày",
            "Đổi số người",
            "Đổi thời lượng",
            "Đổi liệu trình",
            "Đổi giờ",
            "Đổi kỹ thuật viên",
            "Đổi số điện thoại",
        ),
        metadata={"can_change_info": True},
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
        if key in _SAFE_METADATA_KEYS and (value is None or type(value) in {bool, int, float, str}):
            safe[key] = cast(bool | int | float | str | None, value)
    return safe
