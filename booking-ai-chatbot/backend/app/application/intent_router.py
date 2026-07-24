from enum import StrEnum

from app.domain.intent import Intent
from app.domain.nlu import NLUResult


class RouteTarget(StrEnum):
    INFORMATION = "information"
    BOOKING_WORKFLOW = "booking_workflow"
    FAQ = "faq"
    GENERAL = "general"
    CLARIFY = "clarify"
    DENY = "deny"


# Quyết định handler dựa trên structured NLU, không cho LLM tự chọn URL.
def route_intent(result: NLUResult) -> RouteTarget:
    if result.intent in {Intent.SHOP_INFO, Intent.COURSE_INFO, Intent.CHECK_SLOT}:
        return RouteTarget.INFORMATION
    if result.intent in {
        Intent.CREATE_BOOKING,
        Intent.UPDATE_BOOKING,
        Intent.CANCEL_BOOKING,
        Intent.LOOKUP_BOOKING,
    }:
        return RouteTarget.BOOKING_WORKFLOW
    if result.intent is Intent.FAQ:
        return RouteTarget.FAQ
    if result.intent is Intent.GENERAL:
        return RouteTarget.GENERAL
    return RouteTarget.CLARIFY
