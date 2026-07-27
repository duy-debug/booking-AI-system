from __future__ import annotations

from typing import Annotated, Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


class ChatSelection(BaseModel):
    entity: str = Field(..., min_length=1, max_length=64)
    value: Any
    label: str | None = Field(None, max_length=200)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatRequest(BaseModel):
    query: str | None = Field(None, min_length=1, max_length=2000)
    conversation_id: str = Field(default_factory=lambda: str(uuid4()))
    selection: ChatSelection | None = None

    # Bắt buộc request phải có câu nói hoặc một lựa chọn có cấu trúc từ giao diện.
    @model_validator(mode="after")
    def validate_interaction(self) -> "ChatRequest":
        if self.query is None and self.selection is None:
            raise ValueError("query hoặc selection là bắt buộc")
        return self


class UIOption(BaseModel):
    id: str
    label: str
    description: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class UIBlockBase(BaseModel):
    options: list[UIOption] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)


class TextUI(UIBlockBase):
    type: Literal["text"]


class ShopOptionsUI(UIBlockBase):
    type: Literal["shop_options"]


class CourseOptionsUI(UIBlockBase):
    type: Literal["course_options"]


class AddonOptionsUI(UIBlockBase):
    type: Literal["addon_options"]


class PeopleOptionsUI(UIBlockBase):
    type: Literal["people_options"]


class DatePickerUI(UIBlockBase):
    type: Literal["date_picker"]


class SlotOptionsUI(UIBlockBase):
    type: Literal["slot_options"]


class TherapistRequestOptionsUI(UIBlockBase):
    type: Literal["therapist_request_options"]


class TherapistOptionsUI(UIBlockBase):
    type: Literal["therapist_options"]


class GenderOptionsUI(UIBlockBase):
    type: Literal["gender_options"]


class CustomerFormUI(UIBlockBase):
    type: Literal["customer_form"]


class BookingSummaryUI(UIBlockBase):
    type: Literal["booking_summary"]


class ConfirmationUI(UIBlockBase):
    type: Literal["confirmation"]


class BookingResultUI(UIBlockBase):
    type: Literal["booking_result"]


class BookingLookupFormUI(UIBlockBase):
    type: Literal["booking_lookup_form"]


class BookingDetailUI(UIBlockBase):
    type: Literal["booking_detail"]


class BookingCancelFormUI(UIBlockBase):
    type: Literal["booking_cancel_form"]


class BookingCancelSummaryUI(UIBlockBase):
    type: Literal["booking_cancel_summary"]


class BookingUpdateFormUI(UIBlockBase):
    type: Literal["booking_update_form"]


class BookingUpdateSummaryUI(UIBlockBase):
    type: Literal["booking_update_summary"]

UIBlock = Annotated[
    TextUI
    | ShopOptionsUI
    | CourseOptionsUI
    | AddonOptionsUI
    | PeopleOptionsUI
    | DatePickerUI
    | SlotOptionsUI
    | TherapistRequestOptionsUI
    | TherapistOptionsUI
    | GenderOptionsUI
    | CustomerFormUI
    | BookingSummaryUI
    | ConfirmationUI
    | BookingResultUI
    | BookingLookupFormUI
    | BookingDetailUI
    | BookingCancelFormUI
    | BookingCancelSummaryUI
    | BookingUpdateFormUI
    | BookingUpdateSummaryUI,
    Field(discriminator="type"),
]


class ChatResponse(BaseModel):
    contract_version: Literal["1.0"] = "1.0"
    answer: str
    intent: str
    conversation_id: str | None = None
    data: Any | None = None
    missing_entities: list[str] | None = None
    ui: UIBlock | None = None


class HealthResponse(BaseModel):
    status: str


class ApplicationInfoResponse(BaseModel):
    message: str
