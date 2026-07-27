from __future__ import annotations

from typing import Any

from app.application.booking_workflow import BookingWorkflow
from app.application.contracts import ConversationStore
from app.application.create_booking_flow import CreateBookingFlow
from app.application.intent_router import RouteTarget, route_intent
from app.application.lookup_booking_flow import LookupBookingFlow
from app.application.manage_booking_flow import ManageBookingFlow
from app.application.nlu import StructuredNLU
from app.core.exceptions import AppError
from app.domain.intent import Intent
from app.domain.nlu import NLUResult
from app.handlers import (
    BookingConversationHandler,
    ClarificationHandler,
    FAQHandler,
    GeneralHandler,
    InformationHandler,
)
from app.integrations.booking_gateway import HttpBookingGateway
from app.integrations.redis import get_conversation_store
from app.policies.input_guard import guard_input
from app.tools.mutation import MutationTools


class ConversationOrchestrator:
    # Nhận NLU, handler registry và state store tại composition root.
    def __init__(
        self,
        nlu: StructuredNLU,
        handlers: dict[RouteTarget, Any],
        conversation_store: ConversationStore,
    ) -> None:
        self._nlu = nlu
        self._handlers = handlers
        self._store = conversation_store

    # Chạy đúng chuỗi Guard → NLU → Router → Handler được mô tả trong README.
    async def handle(
        self,
        query: str | None,
        conversation_id: str,
        selection: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        nlu_result = await self._resolve_nlu(query, conversation_id, selection)
        target = route_intent(nlu_result)
        handler = self._handlers.get(target) or self._handlers[RouteTarget.CLARIFY]
        if target is RouteTarget.BOOKING_WORKFLOW:
            result = await handler.handle(
                query or "",
                nlu_result,
                conversation_id,
                selection,
            )
        else:
            result = await handler.handle(query or "", nlu_result, conversation_id)
        return {
            **result,
            "intent": nlu_result.intent.value,
            "conversation_id": conversation_id,
        }

    # Khôi phục intent booking cho lựa chọn UI hoặc entity được gửi ở lượt tiếp theo.
    async def _resolve_nlu(
        self,
        query: str | None,
        conversation_id: str,
        selection: dict[str, Any] | None,
    ) -> NLUResult:
        if query:
            guard_input(query)
            result = await self._nlu.parse(query)
            if result.entities and result.intent in {Intent.FAQ, Intent.UNKNOWN}:
                state = await self._store.get_state(conversation_id)
                active_intent = self._active_booking_intent(state.intent)
                if active_intent is not None:
                    result.intent = active_intent
                    result.resource = "booking"
                    result.operation = {
                        Intent.CREATE_BOOKING: "create",
                        Intent.LOOKUP_BOOKING: "lookup",
                        Intent.UPDATE_BOOKING: "update",
                        Intent.CANCEL_BOOKING: "cancel",
                    }[active_intent]
            return result

        state = await self._store.get_state(conversation_id)
        active_intent = self._active_booking_intent(state.intent)
        if selection and active_intent is not None:
            return NLUResult(
                intent=active_intent,
                resource="booking",
                operation={
                    Intent.CREATE_BOOKING: "create",
                    Intent.LOOKUP_BOOKING: "lookup",
                    Intent.UPDATE_BOOKING: "update",
                    Intent.CANCEL_BOOKING: "cancel",
                }[active_intent],
                entities={},
            )
        raise AppError(
            409,
            code="CONVERSATION_NOT_ACTIVE",
            detail="Không tìm thấy workflow đang hoạt động cho lựa chọn này.",
        )

    # Chỉ khôi phục các booking workflow đã được triển khai đầy đủ cho lượt hội thoại tiếp theo.
    @staticmethod
    def _active_booking_intent(intent: str | None) -> Intent | None:
        if intent == Intent.CREATE_BOOKING.value:
            return Intent.CREATE_BOOKING
        if intent == Intent.LOOKUP_BOOKING.value:
            return Intent.LOOKUP_BOOKING
        if intent == Intent.UPDATE_BOOKING.value:
            return Intent.UPDATE_BOOKING
        if intent == Intent.CANCEL_BOOKING.value:
            return Intent.CANCEL_BOOKING
        return None


# Tạo orchestrator mặc định tại composition root mà không đưa FastAPI Depends vào service.
def build_orchestrator() -> ConversationOrchestrator:
    store = get_conversation_store()
    gateway = HttpBookingGateway()
    workflow = BookingWorkflow(
        gateway=gateway,
        conversation_store=store,
    )
    create_booking_flow = CreateBookingFlow(
        conversation_store=store,
        mutation_tools=MutationTools(workflow),
    )
    lookup_booking_flow = LookupBookingFlow(
        conversation_store=store,
        booking_gateway=gateway,
    )
    mutation_tools = MutationTools(workflow)
    update_booking_flow = ManageBookingFlow(
        "update_booking", store, gateway, mutation_tools
    )
    cancel_booking_flow = ManageBookingFlow(
        "cancel_booking", store, gateway, mutation_tools
    )
    return ConversationOrchestrator(
        nlu=StructuredNLU(),
        conversation_store=store,
        handlers={
            RouteTarget.INFORMATION: InformationHandler(),
            RouteTarget.BOOKING_WORKFLOW: BookingConversationHandler(
                create_booking_flow,
                lookup_booking_flow,
                update_booking_flow,
                cancel_booking_flow,
            ),
            RouteTarget.FAQ: FAQHandler(),
            RouteTarget.GENERAL: GeneralHandler(),
            RouteTarget.CLARIFY: ClarificationHandler(),
        },
    )
