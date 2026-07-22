from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import jwt
import pytest

from app.core import auth
from app.core.exceptions import AppError


SECRET = "test-only-secret-with-enough-length"


# Tạo JWT kiểm thử có thời điểm phát hành tùy chỉnh để mô phỏng độ lệch đồng hồ với Supabase.
def _token_with_issued_at(issued_at: datetime) -> str:
    return jwt.encode(
        {
            "sub": "test-user",
            "email": "admin@example.com",
            "iat": issued_at,
            "exp": issued_at + timedelta(minutes=5),
        },
        SECRET,
        algorithm="HS256",
    )


# Thay JWKS bằng khóa cục bộ và cấu hình HS256 để test chỉ tập trung vào quy tắc clock skew.
@pytest.fixture(autouse=True)
def _mock_signing_key(monkeypatch: pytest.MonkeyPatch):
    jwk_client = SimpleNamespace(
        get_signing_key_from_jwt=lambda _token: SimpleNamespace(key=SECRET),
    )
    monkeypatch.setattr(auth, "_jwk_client", lambda: jwk_client)
    monkeypatch.setattr(auth.settings, "JWT_ALGORITHM", "HS256")
    monkeypatch.setattr(auth.settings, "JWT_CLOCK_SKEW_SECONDS", 30)


# Xác nhận token mới hơi vượt đồng hồ backend vẫn được chấp nhận trong dung sai cấu hình.
def test_verify_token_accepts_small_clock_skew():
    token = _token_with_issued_at(datetime.now(timezone.utc) + timedelta(seconds=20))

    payload = auth.verify_supabase_token(token)

    assert payload["sub"] == "test-user"


# Xác nhận dung sai không cho phép token có thời điểm phát hành quá xa trong tương lai.
def test_verify_token_rejects_clock_skew_beyond_limit():
    token = _token_with_issued_at(datetime.now(timezone.utc) + timedelta(seconds=60))

    with pytest.raises(AppError) as exc_info:
        auth.verify_supabase_token(token)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail["detail"] == "Token khong hop le"
