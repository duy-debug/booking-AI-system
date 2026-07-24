# Tests cho tool layer: intent routing, FAQ isolation, confirmation gate

from unittest.mock import patch

import pytest

from app.tools.booking import check_confirmation_intent, get_pending, pop_pending, set_pending
from app.tools.intent import classify_query


class TestIntent:
    def test_intent_faq(self):
        assert classify_query("chinh sach huy the nao?") == "faq"
        assert classify_query("lam the nao de dat lich?") == "faq"
        assert classify_query("quy trinh dat lich?") == "faq"

    def test_intent_shop(self):
        assert classify_query("co chi nhanh nao o Ha Noi?") == "shop_info"
        assert classify_query("dia chi cua hang?") == "shop_info"

    def test_intent_create_booking(self):
        assert classify_query("toi muon dat lich massage") == "create_booking"
        assert classify_query("dat cho") == "create_booking"

    def test_intent_cancel_booking(self):
        assert classify_query("toi muon huy lich") == "cancel_booking"

    def test_intent_update_booking(self):
        assert classify_query("toi muon doi lich") == "update_booking"
        assert classify_query("reschedule") == "update_booking"

    def test_intent_lookup(self):
        assert classify_query("tra cuu lich da dat") == "lookup_booking"

    def test_intent_check_slot(self):
        assert classify_query("con slot trong khong?") == "check_slot"

    def test_intent_course(self):
        assert classify_query("co dich vu massage nao?") == "course_info"
        assert classify_query("co nhung goi nao?") == "course_info"


class TestFAQIsolation:
    async def test_faq_does_not_call_api(self):
        # FAQ chi goi Qdrant + Groq, KHONG goi Booking API
        # Import truoc de patch duoc
        from app.tools import faq as faq_mod

        with patch.object(faq_mod, "answer_faq") as mock_faq:
            mock_faq.return_value = "Tra loi FAQ"
            result = await faq_mod.answer_faq("co dich vu gi?")
            assert "Tra loi" in result
            mock_faq.assert_called_once()


class TestConfirmationGate:
    def test_set_pending(self):
        set_pending("conv1", "create_booking", {"shop_id": "s1"})
        pending = get_pending("conv1")
        assert pending is not None
        assert pending.action == "create_booking"
        assert pending.conversation_id == "conv1"

    def test_pop_pending_removes(self):
        set_pending("conv2", "cancel_booking", {"booking_id": "b1"})
        pending = pop_pending("conv2")
        assert pending is not None
        assert get_pending("conv2") is None

    def test_pop_pending_with_wrong_token_returns_none(self):
        set_pending("conv3", "create_booking", {})
        pending = pop_pending("conv3", token="WRONG")
        assert pending is None
        # Con pending neu token sai
        assert get_pending("conv3") is not None

    def test_pop_pending_with_correct_token(self):
        set_pending("conv4", "create_booking", {})
        pending_before = get_pending("conv4")
        token = pending_before.confirmation_token
        pending = pop_pending("conv4", token=token)
        assert pending is not None
        assert get_pending("conv4") is None

    def test_confirmation_yes(self):
        is_confirm, token = check_confirmation_intent("co")
        assert is_confirm is True
        assert token is None

    def test_confirmation_co(self):
        is_confirm, token = check_confirmation_intent("co")
        assert is_confirm is True

    def test_confirmation_co_dau(self):
        is_confirm, token = check_confirmation_intent("có")
        assert is_confirm is True

    def test_confirmation_no(self):
        is_confirm, token = check_confirmation_intent("khong")
        assert is_confirm is False

    def test_confirmation_token_pattern(self):
        is_confirm, token = check_confirmation_intent("ma xac nhan ABC123DEF456")
        assert is_confirm is True
        assert token == "ABC123DEF456"

    @pytest.mark.asyncio
    async def test_create_booking_requires_confirmation(self):
        # Khoi tao create booking -> khong goi API create ngay
        # Chi goi check_eligibility de pre-check
        with patch("app.integrations.booking_api.check_eligibility") as mock_elig:
            mock_elig.return_value = {"eligible": True}
            with patch("app.integrations.booking_api.create_booking") as mock_create:
                from app.tools.booking import initiate_create_booking

                result = await initiate_create_booking(
                    "conv5",
                    {
                        "customer": {"phone": "0900000000"},
                        "shop_id": "s1",
                    },
                )
                assert "xác nhận" in result or "mã" in result
                # Chua goi API create
                mock_create.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_booking_confirmed_calls_api(self):
        set_pending(
            "conv6",
            "create_booking",
            {
                "shop_id": "s1",
                "booking_date": "2026-07-20",
                "start_time": "10:00",
                "number_of_people": 1,
                "customer": {"phone": "0900000000", "name": "Test"},
                "courses": [{"course_id": "c1", "course_role": "main"}],
                "_idempotency_key": "test-ik",
            },
        )
        with patch("app.integrations.booking_api.create_booking") as mock_create:
            mock_create.return_value = {"booking_id": "b1"}
            from app.tools.booking import confirm_create_booking

            result = await confirm_create_booking("conv6")
            assert "thành công" in result
            mock_create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cancel_booking_requires_confirmation(self):
        from app.tools.booking import initiate_cancel_booking

        result = await initiate_cancel_booking(
            "conv7",
            {
                "booking_id": "b1",
                "cancel_reason": "khong co nhu cau",
            },
        )
        assert "xác nhận" in result or "mã" in result

    @pytest.mark.asyncio
    async def test_cancel_booking_confirmed_calls_api(self):
        set_pending(
            "conv8",
            "cancel_booking",
            {
                "booking_id": "b1",
                "cancel_reason": "test",
            },
        )
        with patch("app.integrations.booking_api.cancel_booking") as mock_cancel:
            mock_cancel.return_value = {"booking_id": "b1"}
            from app.tools.booking import cancel_confirmed_booking

            result = await cancel_confirmed_booking("conv8")
            assert "thành công" in result
            mock_cancel.assert_awaited_once_with(booking_id="b1", reason="test")
