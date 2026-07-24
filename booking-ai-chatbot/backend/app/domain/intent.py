from enum import StrEnum


class Intent(StrEnum):
    FAQ = "faq"
    SHOP_INFO = "shop_info"
    COURSE_INFO = "course_info"
    CHECK_SLOT = "check_slot"
    CREATE_BOOKING = "create_booking"
    UPDATE_BOOKING = "update_booking"
    CANCEL_BOOKING = "cancel_booking"
    LOOKUP_BOOKING = "lookup_booking"
    GENERAL = "general"
    UNKNOWN = "unknown"
