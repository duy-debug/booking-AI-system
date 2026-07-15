# Schemas Pydantic — request & response models
# Tách biệt hoàn toàn với SQLAlchemy models

from .common import (
    PaginationMeta,
    ErrorResponse,
    ValidationErrorDetail,
)

from .shop import ShopCreate, ShopUpdate, ShopResponse, ShopBrief
from .course import CourseCreate, CourseUpdate, CourseResponse
from .therapist import TherapistCreate, TherapistUpdate, TherapistResponse, TherapistBrief
from .therapist_shift import ShiftCreate, ShiftUpdate, ShiftResponse
from .customer import CustomerResponse, CustomerBrief
from .customer_restriction import RestrictionCreate, RestrictionUpdate, RestrictionResponse
from .booking import (
    BookingCourseInput,
    TherapistRequestInput,
    CustomerInput,
    BookingCreate,
    BookingUpdate,
    BookingCancelInput,
    BookingPatchInput,
    BookingEligibilityCheckInput,
    BookingEligibilityCheckResponse,
    BookingResponse,
    BookingListItem,
    ReservationResponse,
    ReservationCourseResponse,
)
from .available_slot import (
    AvailableSlotQuery,
    AvailableSlotResponse,
    AvailableSlotMeta,
    AvailableTherapistQuery,
    AvailableTherapistResponse,
)

__all__ = [
    "PaginationMeta",
    "ErrorResponse",
    "ValidationErrorDetail",
    "ShopCreate",
    "ShopUpdate",
    "ShopResponse",
    "ShopBrief",
    "CourseCreate",
    "CourseUpdate",
    "CourseResponse",
    "TherapistCreate",
    "TherapistUpdate",
    "TherapistResponse",
    "TherapistBrief",
    "ShiftCreate",
    "ShiftUpdate",
    "ShiftResponse",
    "CustomerResponse",
    "CustomerBrief",
    "RestrictionCreate",
    "RestrictionUpdate",
    "RestrictionResponse",
    "BookingCourseInput",
    "TherapistRequestInput",
    "CustomerInput",
    "BookingCreate",
    "BookingUpdate",
    "BookingCancelInput",
    "BookingPatchInput",
    "BookingPatchInput",
    "BookingEligibilityCheckInput",
    "BookingEligibilityCheckResponse",
    "BookingResponse",
    "BookingListItem",
    "ReservationResponse",
    "ReservationCourseResponse",
    "AvailableSlotQuery",
    "AvailableSlotResponse",
    "AvailableSlotMeta",
    "AvailableTherapistQuery",
    "AvailableTherapistResponse",
]
