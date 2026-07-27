from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from app.application.contracts import BookingGateway, ConversationStore
from app.core.exceptions import AppError
from app.domain.nlu import NLUResult
from app.domain.state import ConversationState, ConversationStep

LOOKUP_INTENT = "lookup_booking"
LOOKUP_SELECTION_ENTITIES = frozenset(
    {
        "booking_lookup",
        "booking_id",
        "customer_phone",
    }
)


class LookupBookingFlow:
    # Nhận gateway và state store qua abstraction để workflow không phụ thuộc HTTP hoặc Redis.
    def __init__(
        self,
        conversation_store: ConversationStore,
        booking_gateway: BookingGateway,
    ) -> None:
        self._store = conversation_store
        self._gateway = booking_gateway

    # Thu thập booking ID và số điện thoại, sau đó gọi đúng lookup API không sử dụng OTP.
    async def handle(
        self,
        conversation_id: str,
        nlu: NLUResult,
        selection: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        state = await self._store.get_state(conversation_id)
        if state.intent not in {None, LOOKUP_INTENT}:
            await self._store.delete_pending(conversation_id)
            state = self._reset_state(state)
        elif state.step in {
            ConversationStep.COMPLETED,
            ConversationStep.CANCELLED,
            ConversationStep.FAILED,
        }:
            state = self._reset_state(state)

        state.intent = LOOKUP_INTENT
        state.merge_entities(self._normalize_nlu_entities(nlu.entities))
        if selection:
            self._apply_selection(state, selection)

        missing = self._missing_entities(state)
        if missing:
            state.step = (
                ConversationStep.LOOKUP_COLLECT_BOOKING_ID
                if "booking_id" in missing
                else ConversationStep.LOOKUP_COLLECT_PHONE
            )
            await self._store.save_state(state)
            return self._lookup_form_response(state, missing)

        # Lưu dữ liệu trước khi gọi hệ thống ngoài để khách có thể sửa nếu tra cứu thất bại.
        await self._store.save_state(state)
        booking = await self._gateway.lookup_booking(
            str(state.entities["booking_id"]),
            str(state.entities["customer_phone"]),
        )

        state.step = ConversationStep.COMPLETED
        state.entities = {"booking_id": str(booking["booking_id"])}
        await self._store.save_state(state)
        return {
            "answer": "Đã tìm thấy booking của bạn.",
            "missing_entities": [],
            "data": booking,
            "ui": {
                "type": "booking_detail",
                "options": [],
                "data": booking,
            },
        }

    # Chuẩn hóa entity từ NLU sang tên field thống nhất của lookup workflow.
    @staticmethod
    def _normalize_nlu_entities(entities: dict[str, Any]) -> dict[str, Any]:
        normalized: dict[str, Any] = {}
        if entities.get("booking_id"):
            normalized["booking_id"] = LookupBookingFlow._validate_booking_id(
                entities["booking_id"]
            )
        if entities.get("phone"):
            normalized["customer_phone"] = LookupBookingFlow._validate_phone(
                entities["phone"]
            )
        return normalized

    # Áp dụng dữ liệu có cấu trúc từ frontend và không tin trực tiếp giá trị client gửi lên.
    @staticmethod
    def _apply_selection(
        state: ConversationState,
        selection: dict[str, Any],
    ) -> None:
        entity = str(selection.get("entity", ""))
        value = selection.get("value")
        if entity not in LOOKUP_SELECTION_ENTITIES:
            raise AppError(
                422,
                code="UNSUPPORTED_LOOKUP_SELECTION",
                detail="Loại dữ liệu tra cứu booking không được hỗ trợ.",
            )

        if entity == "booking_lookup":
            if not isinstance(value, dict):
                raise AppError(
                    422,
                    code="INVALID_BOOKING_LOOKUP_DATA",
                    detail="Thông tin tra cứu booking phải là một object.",
                )
            if value.get("booking_id"):
                state.entities["booking_id"] = LookupBookingFlow._validate_booking_id(
                    value["booking_id"]
                )
            if value.get("phone"):
                state.entities["customer_phone"] = LookupBookingFlow._validate_phone(
                    value["phone"]
                )
            return

        if entity == "booking_id":
            state.entities["booking_id"] = LookupBookingFlow._validate_booking_id(value)
            return

        state.entities["customer_phone"] = LookupBookingFlow._validate_phone(value)

    # Kiểm tra booking ID là UUID hợp lệ và chuẩn hóa về dạng chuỗi thống nhất.
    @staticmethod
    def _validate_booking_id(value: Any) -> str:
        try:
            return str(UUID(str(value).strip()))
        except (ValueError, AttributeError) as exc:
            raise AppError(
                422,
                code="INVALID_BOOKING_ID",
                detail="Mã booking không đúng định dạng UUID.",
            ) from exc

    # Kiểm tra số điện thoại theo cùng định dạng Booking Backend đang sử dụng.
    @staticmethod
    def _validate_phone(value: Any) -> str:
        phone = str(value).strip()
        if not re.fullmatch(r"0\d{9,10}", phone):
            raise AppError(
                422,
                code="INVALID_CUSTOMER_PHONE",
                detail="Số điện thoại khách hàng không hợp lệ.",
            )
        return phone

    # Trả danh sách field còn thiếu theo thứ tự booking ID trước, số điện thoại sau.
    @staticmethod
    def _missing_entities(state: ConversationState) -> list[str]:
        return [
            entity
            for entity in ("booking_id", "customer_phone")
            if not state.entities.get(entity)
        ]

    # Tạo contract form để frontend gửi lại booking ID và số điện thoại trong một selection.
    @staticmethod
    def _lookup_form_response(
        state: ConversationState,
        missing: list[str],
    ) -> dict[str, Any]:
        return {
            "answer": "Vui lòng nhập mã booking và số điện thoại đã dùng để đặt lịch.",
            "missing_entities": missing,
            "ui": {
                "type": "booking_lookup_form",
                "options": [],
                "data": {
                    "booking_id": state.entities.get("booking_id"),
                    "phone": state.entities.get("customer_phone"),
                    "required_fields": ["booking_id", "phone"],
                },
            },
        }

    # Bắt đầu workflow mới nhưng giữ version Redis để optimistic concurrency vẫn chính xác.
    @staticmethod
    def _reset_state(state: ConversationState) -> ConversationState:
        return ConversationState(
            conversation_id=state.conversation_id,
            version=state.version,
        )
