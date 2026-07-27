from __future__ import annotations

import re
from datetime import date, time
from typing import Any, Literal
from uuid import UUID

from app.application.contracts import BookingGateway, ConversationStore
from app.core.exceptions import AppError
from app.domain.nlu import NLUResult
from app.domain.state import ConversationState, ConversationStep
from app.tools.mutation import MutationTools

ManageAction = Literal["update_booking", "cancel_booking"]


class ManageBookingFlow:
    """Owner-verified, confirmation-gated update/cancel workflow."""

    def __init__(
        self,
        action: ManageAction,
        conversation_store: ConversationStore,
        booking_gateway: BookingGateway,
        mutation_tools: MutationTools,
    ) -> None:
        self._action = action
        self._store = conversation_store
        self._gateway = booking_gateway
        self._mutations = mutation_tools

    async def handle(
        self,
        conversation_id: str,
        nlu: NLUResult,
        selection: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        state = await self._store.get_state(conversation_id)
        if state.intent not in {None, self._action} or state.step in {
            ConversationStep.COMPLETED,
            ConversationStep.CANCELLED,
            ConversationStep.FAILED,
        }:
            state = ConversationState(conversation_id=conversation_id, version=state.version)
        state.intent = self._action
        state.merge_entities(self._normalize(nlu.entities))

        if selection:
            entity = str(selection.get("entity", ""))
            if entity == "confirmation_token":
                return await self._confirm(state, str(selection.get("value", "")))
            await self._store.delete_pending(conversation_id)
            self._apply_selection(state, entity, selection.get("value"))

        missing_owner = [
            key for key in ("booking_id", "customer_phone") if not state.entities.get(key)
        ]
        if missing_owner:
            await self._store.save_state(state)
            return self._form(state, missing_owner)

        booking = await self._gateway.lookup_booking(
            str(state.entities["booking_id"]),
            str(state.entities["customer_phone"]),
        )
        if booking.get("status") == "cancelled":
            raise AppError(409, code="BOOKING_ALREADY_CANCELLED", detail="Booking đã được hủy.")

        if self._action == "update_booking" and not any(
            state.entities.get(key) for key in ("booking_date", "start_time")
        ):
            await self._store.save_state(state)
            return self._form(state, ["booking_date", "start_time"], booking)

        payload = self._payload(state)
        if self._action == "update_booking":
            effective_date = str(
                payload.get("booking_date") or booking["booking_date"]
            )
            effective_time = str(
                payload.get("start_time") or booking["start_time"]
            )[:5]
            if not await self._gateway.is_reschedule_available(
                booking, effective_date, effective_time
            ):
                raise AppError(
                    409,
                    code="RESCHEDULE_SLOT_UNAVAILABLE",
                    detail="Khung giờ mới không còn khả dụng.",
                )
        pending = await self._mutations.prepare(
            conversation_id,
            self._action,
            {"booking_id": str(booking["booking_id"]), **payload},
        )
        state.step = ConversationStep.AWAIT_CONFIRMATION
        await self._store.save_state(state)
        summary_type = (
            "booking_cancel_summary"
            if self._action == "cancel_booking"
            else "booking_update_summary"
        )
        return {
            "answer": (
                "Vui lòng xác nhận hủy booking."
                if self._action == "cancel_booking"
                else "Vui lòng xác nhận thay đổi booking."
            ),
            "missing_entities": [],
            "ui": {
                "type": summary_type,
                "options": [
                    {
                        "id": pending.confirmation_token,
                        "label": "Xác nhận",
                        "metadata": {},
                    }
                ],
                "data": {
                    "booking": booking,
                    "changes": payload,
                    "confirmation_token": pending.confirmation_token,
                },
            },
        }

    async def _confirm(
        self, state: ConversationState, confirmation_token: str
    ) -> dict[str, Any]:
        result = await self._mutations.confirm(
            state.conversation_id, confirmation_token.upper()
        )
        state.step = (
            ConversationStep.CANCELLED
            if self._action == "cancel_booking"
            else ConversationStep.COMPLETED
        )
        await self._store.save_state(state)
        return {
            "answer": (
                "Đã hủy booking thành công."
                if self._action == "cancel_booking"
                else "Đã cập nhật booking thành công."
            ),
            "missing_entities": [],
            "data": result,
            "ui": {
                "type": "booking_result",
                "options": [],
                "data": result,
            },
        }

    @staticmethod
    def _normalize(entities: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if entities.get("booking_id"):
            result["booking_id"] = ManageBookingFlow._booking_id(entities["booking_id"])
        if entities.get("phone"):
            result["customer_phone"] = ManageBookingFlow._phone(entities["phone"])
        if entities.get("booking_date"):
            result["booking_date"] = ManageBookingFlow._date(entities["booking_date"])
        if entities.get("start_time"):
            result["start_time"] = ManageBookingFlow._time(entities["start_time"])
        return result

    @staticmethod
    def _apply_selection(
        state: ConversationState, entity: str, value: Any
    ) -> None:
        if entity != "booking_manage" or not isinstance(value, dict):
            raise AppError(
                422,
                code="UNSUPPORTED_MANAGE_SELECTION",
                detail="Dữ liệu cập nhật booking không hợp lệ.",
            )
        if value.get("booking_id"):
            state.entities["booking_id"] = ManageBookingFlow._booking_id(
                value["booking_id"]
            )
        if value.get("phone"):
            state.entities["customer_phone"] = ManageBookingFlow._phone(value["phone"])
        if value.get("booking_date"):
            state.entities["booking_date"] = ManageBookingFlow._date(
                value["booking_date"]
            )
        if value.get("start_time"):
            state.entities["start_time"] = ManageBookingFlow._time(value["start_time"])
        if "cancel_reason" in value:
            state.entities["cancel_reason"] = str(value["cancel_reason"] or "").strip()[:500]

    def _payload(self, state: ConversationState) -> dict[str, Any]:
        if self._action == "cancel_booking":
            return {
                "status": "cancelled",
                "cancel_reason": state.entities.get("cancel_reason") or None,
            }
        return {
            key: state.entities[key]
            for key in ("booking_date", "start_time")
            if state.entities.get(key)
        }

    def _form(
        self,
        state: ConversationState,
        missing: list[str],
        booking: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "answer": (
                "Nhập mã booking và số điện thoại để hủy lịch."
                if self._action == "cancel_booking"
                else "Nhập thông tin booking và ngày hoặc giờ mới."
            ),
            "missing_entities": missing,
            "ui": {
                "type": (
                    "booking_cancel_form"
                    if self._action == "cancel_booking"
                    else "booking_update_form"
                ),
                "options": [],
                "data": {
                    "booking_id": state.entities.get("booking_id"),
                    "phone": state.entities.get("customer_phone"),
                    "booking": booking,
                    "required_fields": missing,
                },
            },
        }

    @staticmethod
    def _booking_id(value: Any) -> str:
        try:
            return str(UUID(str(value).strip()))
        except (ValueError, AttributeError) as exc:
            raise AppError(
                422, code="INVALID_BOOKING_ID", detail="Mã booking không hợp lệ."
            ) from exc

    @staticmethod
    def _phone(value: Any) -> str:
        phone = str(value).strip()
        if not re.fullmatch(r"0\d{9,10}", phone):
            raise AppError(422, code="INVALID_CUSTOMER_PHONE", detail="Số điện thoại không hợp lệ.")
        return phone

    @staticmethod
    def _date(value: Any) -> str:
        try:
            parsed = date.fromisoformat(str(value))
        except ValueError as exc:
            raise AppError(
                422,
                code="INVALID_BOOKING_DATE",
                detail="Ngày phải có dạng YYYY-MM-DD.",
            ) from exc
        if parsed < date.today():
            raise AppError(
                422,
                code="BOOKING_DATE_IN_PAST",
                detail="Ngày mới không được ở quá khứ.",
            )
        return parsed.isoformat()

    @staticmethod
    def _time(value: Any) -> str:
        try:
            return time.fromisoformat(str(value)).strftime("%H:%M")
        except ValueError as exc:
            raise AppError(
                422, code="INVALID_START_TIME", detail="Giờ phải có dạng HH:MM."
            ) from exc
