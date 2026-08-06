"""Tests for temporary booking conversation data."""

from datetime import date, time
from decimal import Decimal
from uuid import UUID

import pytest

from app.domain.booking_context import BookingContext
from app.domain.booking_models import (
    BookingOption,
    Course,
    CourseSelection,
    CourseType,
    Customer,
    InvalidBookingDataError,
    InvalidCustomerCountError,
    InvalidDurationError,
    Shop,
    TherapistNotAllowedForGroupError,
    TherapistPreference,
    TherapistPreferenceType,
)
from app.domain.booking_state import BookingState

SHOP = Shop(
    shop_id=UUID("11111111-1111-1111-1111-111111111111"),
    name="Central Spa",
)
COURSE = Course(
    course_id=UUID("22222222-2222-2222-2222-222222222222"),
    name="Aromatherapy",
    duration_minutes=60,
    price=Decimal("500000.00"),
)
CUSTOMER = Customer(phone="0901234567", name="Nguyen An")
BOOKING_ID = UUID("33333333-3333-3333-3333-333333333333")
ADDON = Course(
    course_id=UUID("44444444-4444-4444-4444-444444444444"),
    name="Essential oil",
    duration_minutes=15,
    price=Decimal("100000.00"),
    course_type=CourseType.ADDON,
)
OTHER_SHOP = Shop(
    shop_id=UUID("55555555-5555-5555-5555-555555555555"),
    name="Riverside Spa",
)
THERAPIST = TherapistPreference(TherapistPreferenceType.FEMALE)


def make_ready_context() -> BookingContext:
    return BookingContext(
        conversation_id="conversation-1",
        state=BookingState.AWAITING_CONFIRMATION,
        shop=SHOP,
        main_course=COURSE,
        customer=CUSTOMER,
        booking_date=date(2026, 8, 1),
        start_time=time(10, 30),
        num_customer=1,
        duration_minutes=60,
        phone="0901234567",
        phone_confirmed=True,
        ng_list_checked=True,
    )


def make_change_context() -> BookingContext:
    context = make_ready_context()
    context.addons = (ADDON,)
    context.options = (BookingOption("option-1", "Hot towel"),)
    context.available_slots = (time(10, 30), time(11, 0))
    context.therapist_preference = THERAPIST
    context.therapist_verified = True
    return context


def test_change_shop_clears_shop_dependencies_only() -> None:
    context = make_change_context()

    context.change_shop(OTHER_SHOP)

    assert context.shop is OTHER_SHOP
    assert context.main_course is None
    assert context.addons == ()
    assert context.available_slots is None
    assert context.start_time is None
    assert context.therapist_preference is None
    assert context.booking_date == date(2026, 8, 1)
    assert context.num_customer == 1
    assert context.duration_minutes == 60


def test_change_date_preserves_shop_service_and_other_independent_values() -> None:
    context = make_change_context()

    context.change_booking_date(date(2026, 8, 2))

    assert context.booking_date == date(2026, 8, 2)
    assert context.shop is SHOP
    assert context.main_course is COURSE
    assert context.num_customer == 1
    assert context.start_time is None
    assert context.therapist_preference is None


def test_change_people_clears_slot_and_therapist_but_preserves_course() -> None:
    context = make_change_context()

    context.change_num_customer(2)

    assert context.num_customer == 2
    assert context.shop is SHOP
    assert context.main_course is COURSE
    assert context.booking_date == date(2026, 8, 1)
    assert context.start_time is None
    assert context.therapist_preference is None


def test_invalid_change_people_is_atomic() -> None:
    context = make_change_context()

    with pytest.raises(InvalidCustomerCountError):
        context.change_num_customer(5)

    assert context.num_customer == 1
    assert context.start_time == time(10, 30)
    assert context.therapist_preference is THERAPIST


def test_change_duration_clears_course_but_preserves_shop() -> None:
    context = make_change_context()

    context.change_duration(90)

    assert context.duration_minutes == 90
    assert context.shop is SHOP
    assert context.main_course is None
    assert context.start_time is None


def test_change_course_preserves_shop_and_invalidates_availability() -> None:
    context = make_change_context()

    context.change_course_selection(None)

    assert context.shop is SHOP
    assert context.main_course is None
    assert context.available_slots is None
    assert context.start_time is None


def test_change_time_preserves_date_and_available_slots() -> None:
    context = make_change_context()

    context.change_start_time(time(11, 0))

    assert context.booking_date == date(2026, 8, 1)
    assert context.available_slots == (time(10, 30), time(11, 0))
    assert context.start_time == time(11, 0)
    assert context.therapist_preference is None


def test_change_therapist_preserves_selected_slot() -> None:
    context = make_change_context()
    replacement = TherapistPreference(TherapistPreferenceType.MALE)

    context.change_therapist_preference(replacement)

    assert context.start_time == time(10, 30)
    assert context.therapist_preference is replacement
    assert context.therapist_verified is False


def test_change_phone_preserves_booking_selection() -> None:
    context = make_change_context()

    context.change_phone(None)

    assert context.phone is None
    assert context.customer is None
    assert context.phone_confirmed is False
    assert context.shop is SHOP
    assert context.main_course is COURSE
    assert context.booking_date == date(2026, 8, 1)
    assert context.start_time == time(10, 30)


def test_new_context_starts_idle() -> None:
    context = BookingContext(conversation_id="conversation-1")

    assert context.state is BookingState.IDLE


def test_booking_fields_default_to_none() -> None:
    context = BookingContext(conversation_id="conversation-1")

    assert context.shop is None
    assert context.main_course is None
    assert context.customer is None
    assert context.booking_date is None
    assert context.start_time is None
    assert context.booking_id is None
    assert context.num_customer is None
    assert context.duration_minutes is None
    assert context.therapist_preference is None
    assert context.therapist_verified is False
    assert context.options == ()
    assert context.addons == ()
    assert context.available_slots is None
    assert context.phone is None
    assert context.phone_confirmed is False
    assert context.member_rank is None
    assert context.visit_count is None
    assert context.ng_list_checked is False
    assert context.is_ng_customer is False
    assert context.booking is None
    assert context.reservation_code is None
    assert context.reservation_codes == ()
    assert context.child_reservation_ids == ()
    assert context.pending_action is None


def test_context_is_not_ready_when_data_is_missing() -> None:
    context = make_ready_context()
    context.start_time = None

    assert context.is_ready_to_create() is False


def test_context_is_ready_when_required_data_is_present() -> None:
    assert make_ready_context().is_ready_to_create() is True


def test_reset_clears_temporary_booking_data() -> None:
    context = make_ready_context()
    context.booking_id = BOOKING_ID
    context.visit_count = 7
    context.reservation_codes = ("RSV-1",)
    context.child_reservation_ids = (BOOKING_ID,)
    context.pending_action = "create_booking"
    context.requested_booking_date = date(2099, 8, 1)
    context.requested_start_time = time(7, 0)

    context.reset()

    assert context.state is BookingState.IDLE
    assert context.shop is None
    assert context.main_course is None
    assert context.customer is None
    assert context.booking_date is None
    assert context.requested_booking_date is None
    assert context.start_time is None
    assert context.requested_start_time is None
    assert context.booking_id is None
    assert context.num_customer is None
    assert context.duration_minutes is None
    assert context.therapist_preference is None
    assert context.therapist_verified is False
    assert context.options == ()
    assert context.addons == ()
    assert context.available_slots is None
    assert context.phone is None
    assert context.phone_confirmed is False
    assert context.member_rank is None
    assert context.visit_count is None
    assert context.ng_list_checked is False
    assert context.is_ng_customer is False
    assert context.booking is None
    assert context.reservation_code is None
    assert context.reservation_codes == ()
    assert context.child_reservation_ids == ()
    assert context.pending_action is None


def test_reset_preserves_conversation_id() -> None:
    context = make_ready_context()

    context.reset()

    assert context.conversation_id == "conversation-1"


def test_turn_sequence_increments_and_survives_booking_reset() -> None:
    context = BookingContext(conversation_id="conversation-1")

    assert context.begin_turn() == 1
    assert context.begin_turn() == 2

    context.reset()

    assert context.turn_sequence == 2


def test_context_data_is_mutable() -> None:
    context = BookingContext(conversation_id="conversation-1")

    context.shop = SHOP
    context.state = BookingState.SELECTING_DATE

    assert context.shop is SHOP
    assert context.state is BookingState.SELECTING_DATE


def test_slots_prevent_adding_undeclared_attributes() -> None:
    context = BookingContext(conversation_id="conversation-1")

    assert not hasattr(context, "__dict__")
    with pytest.raises(AttributeError):
        context.unexpected = "value"  # type: ignore[attr-defined]


@pytest.mark.parametrize("value", [0, -1, 4])
def test_set_num_customer_rejects_invalid_value(value: int) -> None:
    context = BookingContext(conversation_id="conversation-1", num_customer=1)

    with pytest.raises(InvalidCustomerCountError):
        context.set_num_customer(value)

    assert context.num_customer == 1


@pytest.mark.parametrize("value", [0, -15, 20, 50])
def test_set_duration_rejects_invalid_value(value: int) -> None:
    context = BookingContext(conversation_id="conversation-1")

    with pytest.raises(InvalidDurationError):
        context.set_duration(value)


def test_context_phone_confirmation_lifecycle() -> None:
    context = BookingContext(conversation_id="conversation-1")

    context.set_phone("0901234567")
    assert context.phone == "0901234567"
    assert context.phone_confirmed is False

    context.confirm_phone()
    assert context.phone_confirmed is True

    context.clear_phone()
    assert context.phone is None
    assert context.phone_confirmed is False


def test_confirm_phone_requires_phone() -> None:
    context = BookingContext(conversation_id="conversation-1")

    with pytest.raises(InvalidBookingDataError):
        context.confirm_phone()


def test_context_sets_immutable_options_and_invalidates_therapist() -> None:
    context = BookingContext(conversation_id="conversation-1")
    preference = TherapistPreference(TherapistPreferenceType.FEMALE)
    option = BookingOption(option_id="oil", name="Essential oil")

    context.set_therapist_preference(preference)
    context.set_options((option,))

    assert context.therapist_preference is None
    assert context.options == (option,)
    assert isinstance(context.options, tuple)


def test_context_rejects_duplicate_options() -> None:
    context = BookingContext(conversation_id="conversation-1")

    with pytest.raises(InvalidBookingDataError):
        context.set_options(
            (
                BookingOption(option_id="oil", name="Oil"),
                BookingOption(option_id="oil", name="Duplicate"),
            )
        )


@pytest.mark.parametrize("value", [1, 2, 3])
def test_set_num_customer_accepts_supported_values(value: int) -> None:
    context = BookingContext(conversation_id="conversation-1")

    context.set_num_customer(value)

    assert context.num_customer == value


def test_changing_to_group_clears_therapist_time_and_slots() -> None:
    for group_size in (2, 3):
        context = make_ready_context()
        context.therapist_preference = TherapistPreference(
            TherapistPreferenceType.PERSONAL,
            therapist_name="Mai",
        )
        context.therapist_verified = True
        context.available_slots = (time(10, 30),)

        context.set_num_customer(group_size)

        assert context.num_customer == group_size
        assert context.therapist_preference is None
        assert context.therapist_verified is False
        assert context.start_time is None
        assert context.available_slots is None


def test_group_accepts_gender_but_rejects_personal_therapist() -> None:
    context = BookingContext(conversation_id="conversation-1", num_customer=2)

    context.set_therapist_preference(
        TherapistPreference(TherapistPreferenceType.FEMALE)
    )

    assert context.therapist_preference == TherapistPreference(
        TherapistPreferenceType.FEMALE
    )

    with pytest.raises(TherapistNotAllowedForGroupError):
        context.set_therapist_preference(
            TherapistPreference(
                TherapistPreferenceType.PERSONAL,
                therapist_name="Mai",
            )
        )


@pytest.mark.parametrize("duration", [30, 45, 60, 75])
def test_set_duration_accepts_supported_values(duration: int) -> None:
    context = BookingContext(conversation_id="conversation-1")

    context.set_duration(duration)

    assert context.duration_minutes == duration


def test_set_phone_resets_all_customer_verification() -> None:
    context = make_ready_context()
    context.member_rank = "gold"
    context.is_ng_customer = True

    context.set_phone("0912345678")

    assert context.phone == "0912345678"
    assert context.phone_confirmed is False
    assert context.member_rank is None
    assert context.ng_list_checked is False
    assert context.is_ng_customer is False


def test_set_customer_verification_stores_external_result() -> None:
    context = BookingContext(conversation_id="conversation-1", phone="0901234567")

    context.set_customer_verification(
        member_rank="gold",
        visit_count=7,
        is_ng_customer=False,
    )

    assert context.member_rank == "gold"
    assert context.visit_count == 7
    assert context.ng_list_checked is True
    assert context.is_ng_customer is False


def test_customer_verification_requires_phone() -> None:
    context = BookingContext(conversation_id="conversation-1")

    with pytest.raises(InvalidBookingDataError):
        context.set_customer_verification(member_rank=None, is_ng_customer=False)


def test_changing_shop_keeps_date_and_clears_dependent_data() -> None:
    context = make_ready_context()
    context.addons = (ADDON,)
    context.available_slots = (time(10, 30),)
    context.therapist_preference = TherapistPreference(
        TherapistPreferenceType.FEMALE
    )
    context.member_rank = "gold"
    context.visit_count = 7
    context.ng_list_checked = True

    context.set_shop(OTHER_SHOP)

    assert context.shop is OTHER_SHOP
    assert context.booking_date == date(2026, 8, 1)
    assert context.member_rank is None
    assert context.visit_count is None
    assert context.ng_list_checked is False
    assert_course_and_availability_cleared(context)


def test_changing_date_clears_course_and_availability() -> None:
    context = make_ready_context()
    context.addons = (ADDON,)
    context.available_slots = (time(10, 30),)
    context.therapist_preference = TherapistPreference(
        TherapistPreferenceType.FEMALE
    )

    context.set_booking_date(date(2026, 8, 2))

    assert context.booking_date == date(2026, 8, 2)
    assert_course_and_availability_cleared(context)


def test_changing_duration_clears_course_and_availability() -> None:
    context = make_ready_context()
    context.addons = (ADDON,)
    context.available_slots = (time(10, 30),)
    context.therapist_preference = TherapistPreference(
        TherapistPreferenceType.FEMALE
    )

    context.set_duration(75)

    assert context.duration_minutes == 75
    assert_course_and_availability_cleared(context)


def test_changing_course_clears_slots_time_and_therapist() -> None:
    context = make_ready_context()
    context.available_slots = (time(10, 30),)
    context.therapist_preference = TherapistPreference(
        TherapistPreferenceType.FEMALE
    )

    context.set_course_selection(CourseSelection(COURSE, (ADDON,)))

    assert context.main_course is COURSE
    assert context.addons == (ADDON,)
    assert context.available_slots is None
    assert context.start_time is None
    assert context.therapist_preference is None
    assert context.therapist_verified is False


def test_changing_time_requires_therapist_revalidation() -> None:
    context = make_ready_context()
    preference = TherapistPreference(TherapistPreferenceType.FEMALE)
    context.therapist_preference = preference
    context.therapist_verified = True

    context.set_start_time(time(11, 0))

    assert context.start_time == time(11, 0)
    assert context.therapist_preference is preference
    assert context.therapist_verified is False


@pytest.mark.parametrize(
    "missing_field",
    [
        "shop",
        "booking_date",
        "num_customer",
        "duration_minutes",
        "main_course",
        "start_time",
        "phone",
    ],
)
def test_readiness_rejects_each_missing_required_field(missing_field: str) -> None:
    context = make_ready_context()
    setattr(context, missing_field, None)

    assert context.is_ready_to_create() is False


def test_readiness_requires_phone_confirmation() -> None:
    context = make_ready_context()
    context.phone_confirmed = False

    assert context.is_ready_to_create() is False


def test_readiness_requires_ng_verification() -> None:
    context = make_ready_context()
    context.ng_list_checked = False

    assert context.is_ready_to_create() is False


def test_readiness_rejects_ng_customer() -> None:
    context = make_ready_context()
    context.is_ng_customer = True

    assert context.is_ready_to_create() is False


@pytest.mark.parametrize("group_size", [2, 3])
def test_group_without_therapist_is_ready(group_size: int) -> None:
    context = make_ready_context()
    context.num_customer = group_size

    assert context.is_ready_to_create() is True


def test_group_with_therapist_is_not_ready() -> None:
    context = make_ready_context()
    context.num_customer = 2
    context.therapist_preference = TherapistPreference(
        TherapistPreferenceType.FEMALE
    )

    assert context.is_ready_to_create() is False


def assert_course_and_availability_cleared(context: BookingContext) -> None:
    assert context.main_course is None
    assert context.addons == ()
    assert context.options == ()
    assert context.available_slots is None
    assert context.start_time is None
    assert context.therapist_preference is None
    assert context.therapist_verified is False
