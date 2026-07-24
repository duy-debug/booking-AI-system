from app.core.exceptions import AppError

PUBLIC_TOOLS = frozenset(
    {
        "list_shops",
        "get_shop",
        "list_courses",
        "get_available_slots",
        "get_available_therapists",
        "check_eligibility",
        "create_booking",
        "get_booking",
        "list_bookings",
        "update_booking",
        "cancel_booking",
    }
)


# Chặn mọi tool không thuộc allowlist công khai trước khi application thực thi.
def ensure_public_tool(tool_name: str) -> None:
    if tool_name not in PUBLIC_TOOLS:
        raise AppError(
            403,
            code="TOOL_NOT_ALLOWED",
            detail="Chatbot không được phép thực thi công cụ này.",
        )
