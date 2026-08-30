"""Validate selected time and therapist choices."""

from datetime import time

from app.domain.booking_context import BookingContext
from app.domain.booking_models import TherapistPreference, TherapistPreferenceType
from app.domain.outcomes import HandlerOutcome, HandlerResult


# Use case cập nhật ngày/giờ trong context;
# validate slot thật do availability handler đảm nhiệm.
class SelectScheduleHandler:
    """Applies only schedule choices already verified against context data."""

    # Chỉ chấp nhận giờ nằm trong latest available_slots đã load từ POS.
    def select_time(self, context: BookingContext, value: time) -> HandlerResult:
        if context.available_slots is None or value not in context.available_slots:
            return HandlerResult(
                HandlerOutcome.CONFLICT,
                {"available_slots": context.available_slots or ()},
                error_code="slot_unavailable",
            )
        return HandlerResult(
            HandlerOutcome.SUCCESS,
            context_updates={"start_time": value},
        )

    # Validate therapist theo chính sách: group booking không chọn therapist cá nhân.
    def select_therapist(
        self,
        context: BookingContext,
        preference: TherapistPreference | None,
    ) -> HandlerResult:
        if context.num_customer is None:
            return HandlerResult(
                HandlerOutcome.INVALID_INPUT,
                error_code="people_count_required",
            )
        if (
            context.num_customer >= 2
            and preference is not None
            and preference.preference_type is not TherapistPreferenceType.NONE
        ):
            return HandlerResult(
                HandlerOutcome.INVALID_INPUT,
                error_code="group_therapist_not_allowed",
            )
        if (
            preference is not None
            and preference.preference_type is TherapistPreferenceType.PERSONAL
            and not preference.therapist_id
        ):
            return HandlerResult(
                HandlerOutcome.INVALID_INPUT,
                error_code="therapist_unverified",
            )
        if context.num_customer >= 2:
            preference = TherapistPreference(TherapistPreferenceType.NONE)
        return HandlerResult(
            HandlerOutcome.SUCCESS,
            context_updates={
                "therapist_preference": preference,
                "therapist_verified": True,
            },
        )
