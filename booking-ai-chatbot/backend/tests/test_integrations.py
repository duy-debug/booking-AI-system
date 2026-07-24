# Tests cho integrations layer: timeout, HTTP errors, RFC 9457 mapping
# Dung AsyncMock de mock httpx.AsyncClient ma khong can async fixture

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.core.exceptions import AppError
from app.integrations import booking_api as api


def _fake_response(status_code: int, json_body: dict) -> httpx.Response:
    return httpx.Response(status_code=status_code, content=json.dumps(json_body))


@pytest.mark.asyncio
class TestBookingAPIClient:
    @pytest.fixture(autouse=True)
    def _mock_http(self):
        # Mock get_client() de tra ve mock httpx.AsyncClient
        with patch("app.integrations.booking_api.get_client") as mock_get:
            mock_http = AsyncMock(spec=httpx.AsyncClient)
            mock_get.return_value = mock_http
            self.http = mock_http
            yield

    async def test_list_shops_empty_ok(self):
        self.http.request.return_value = _fake_response(200, {"data": []})
        result = await api.list_shops()
        assert result == []

    async def test_timeout_raises_503(self):
        self.http.request.side_effect = httpx.TimeoutException("timeout")
        with pytest.raises(AppError) as exc:
            await api.list_shops()
        assert exc.value.status_code == 503
        assert "TIMEOUT" in exc.value.detail.get("code", "")

    async def test_request_error_raises_502(self):
        self.http.request.side_effect = httpx.RequestError("connection refused")
        with pytest.raises(AppError) as exc:
            await api.list_shops()
        assert exc.value.status_code == 502

    async def test_404_from_backend(self):
        self.http.request.return_value = _fake_response(
            404,
            {
                "code": "SHOP_NOT_FOUND",
                "detail": "Khong tim thay shop",
            },
        )
        with pytest.raises(AppError) as exc:
            await api.get_shop("nonexistent")
        assert exc.value.status_code == 404
        assert "NOT_FOUND" in exc.value.detail.get("code", "")

    async def test_422_validation_from_backend(self):
        self.http.request.return_value = _fake_response(
            422,
            {
                "code": "VALIDATION_ERROR",
                "detail": "Invalid date format",
            },
        )
        with pytest.raises(AppError) as exc:
            await api.get_available_slots(
                shop_id="s1",
                booking_date="invalid",
                number_of_people=1,
                main_course_id="c1",
            )
        assert exc.value.status_code == 422

    async def test_409_conflict_from_backend(self):
        self.http.request.return_value = _fake_response(
            409,
            {
                "code": "SLOT_CONFLICT",
                "detail": "Slot da co nguoi dat",
            },
        )
        with pytest.raises(AppError) as exc:
            await api.create_booking({"shop_id": "s1"})
        assert exc.value.status_code == 409

    async def test_403_ng_list_from_backend(self):
        self.http.request.return_value = _fake_response(
            403,
            {
                "code": "CUSTOMER_IN_NG_LIST",
                "detail": "So dien thoai khong duoc phep dat booking",
            },
        )
        with pytest.raises(AppError) as exc:
            await api.check_eligibility(phone="ng123", shop_id="s1")
        assert exc.value.status_code == 403

    async def test_rfc9457_mapping(self):
        self.http.request.return_value = _fake_response(
            404,
            {
                "type": "about:blank",
                "title": "Error",
                "status": 404,
                "detail": "Khong tim thay booking",
                "code": "BOOKING_NOT_FOUND",
            },
        )
        with pytest.raises(AppError) as exc:
            await api.get_booking("nonexistent")
        assert "Khong tim thay" in exc.value.detail.get("detail", "")
