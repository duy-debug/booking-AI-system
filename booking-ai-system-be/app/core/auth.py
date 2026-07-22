# Auth — verify Supabase Auth JWT (asymmetric, qua JWKS), phân quyền admin theo email whitelist

from functools import lru_cache

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from app.core.config import settings
from app.core.exceptions import AppError

# Tự động parse Authorization: Bearer <token>
bearer_scheme = HTTPBearer(auto_error=False)


# Khởi tạo và cache JWKS client để tái sử dụng public key khi xác thực nhiều request.
@lru_cache(maxsize=1)
def _jwk_client() -> PyJWKClient:
    return PyJWKClient(settings.SUPABASE_JWKS_URL)


# Xác minh chữ ký và hạn sử dụng của Supabase JWT, sau đó trả payload người dùng đã tin cậy.
def verify_supabase_token(token: str) -> dict:
    try:
        signing_key = _jwk_client().get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=[settings.JWT_ALGORITHM],
            options={"verify_aud": False},
        )
    except jwt.ExpiredSignatureError:
        raise AppError(401, code="AUTHENTICATION_REQUIRED", detail="Token het han")
    except jwt.InvalidTokenError:
        raise AppError(401, code="AUTHENTICATION_REQUIRED", detail="Token khong hop le")


# Đọc Bearer token từ request và trả payload của người dùng đã đăng nhập.
def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict:
    if credentials is None:
        raise AppError(401, code="AUTHENTICATION_REQUIRED", detail="Thieu Authorization header")
    return verify_supabase_token(credentials.credentials)


# Xác thực token và chỉ cho phép email nằm trong danh sách tài khoản quản trị cấu hình sẵn.
def require_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict:
    if credentials is None:
        raise AppError(401, code="AUTHENTICATION_REQUIRED", detail="Thieu Authorization header")
    payload = verify_supabase_token(credentials.credentials)
    email = payload.get("email")
    if not email or email not in settings.ADMIN_EMAILS:
        raise AppError(403, code="FORBIDDEN", detail="Tai khoan khong co quyen admin")
    return payload
