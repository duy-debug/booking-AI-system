"""Central masking and redaction for POS observability."""

import re
from collections.abc import Mapping

# Nhận diện số điện thoại trong text tự do, kể cả có dấu cách hoặc dấu gạch ngang.
_PHONE = re.compile(r"(?<!\d)\+?\d(?:[ -]?\d){8,14}(?!\d)")
# Nhận diện email để che phần tên người dùng nhưng vẫn giữ domain phục vụ debug.
_EMAIL = re.compile(r"\b([^\s@])[^\s@]*@([^\s@]+)\b")
# Nhận diện Bearer token trong header/message log để tránh lộ credential truy cập.
_BEARER = re.compile(r"(?i)\bBearer\s+[^\s,;]+")
# Nhận diện UUID để bảo vệ tạm thời, tránh bị regex số điện thoại che nhầm một phần ID.
_UUID = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)


# Che số điện thoại nhưng giữ vài chữ số đầu/cuối để developer vẫn đối chiếu được log.
def mask_phone(value: str) -> str:
    digits = "".join(character for character in value if character.isdigit())
    return f"{digits[:3]}***{digits[-4:]}" if len(digits) >= 7 else "***"


# Che email theo cách vẫn giữ domain để debug nguồn dữ liệu mà không lộ local-part.
def mask_email(value: str) -> str:
    match = _EMAIL.fullmatch(value.strip())
    return f"{match.group(1)}***@{match.group(2)}" if match else "***"


# Redact header nhạy cảm như authorization/cookie trước khi ghi log request.
def redact_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {
        key: "***" if _secret_key(key) else sanitize_text(value)
        for key, value in headers.items()
    }


# Sanitize toàn bộ mapping theo từng key để giữ cấu trúc log nhưng không lộ dữ liệu nhạy cảm.
def sanitize_dict(values: Mapping[str, object]) -> dict[str, object]:
    return {str(key): sanitize_value(str(key), value) for key, value in values.items()}


# Sanitize giá trị bất kỳ dựa trên tên field; phone/email/secret có rule che riêng.
def sanitize_value(key: str, value: object) -> object:
    normalized = key.casefold().replace("-", "_")
    # Secret và idempotency key không cần giữ một phần giá trị vì có thể dùng lại để gọi hệ thống.
    if _secret_key(normalized) or "idempotency" in normalized:
        return "***"
    if "phone" in normalized:
        return mask_phone(str(value)) if value is not None else None
    if "email" in normalized:
        return mask_email(str(value)) if value is not None else None
    if isinstance(value, str):
        return sanitize_text(value)
    if isinstance(value, Mapping):
        return sanitize_dict(value)
    # Với collection, sanitize từng item để log nested payload vẫn an toàn.
    if isinstance(value, list | tuple | set | frozenset):
        return [sanitize_value(key, item) for item in value]
    if value is None or isinstance(value, bool | int | float):
        return value
    return str(value)


# Sanitize message tự do trong log, ưu tiên giữ UUID để trace kỹ thuật không bị mất.
def sanitize_text(value: str) -> str:
    protected: list[str] = []
    # UUID được bảo vệ tạm thời để regex phone không vô tình che một phần chuỗi định danh.
    sanitized = _UUID.sub(lambda match: _protect(match.group(0), protected), value)
    sanitized = _BEARER.sub("Bearer ***", sanitized)
    sanitized = _PHONE.sub(lambda match: mask_phone(match.group(0)), sanitized)
    sanitized = _EMAIL.sub(
        lambda match: f"{match.group(1)}***@{match.group(2)}", sanitized
    )
    return _restore(sanitized, protected)


# Chuẩn hóa thông tin exception trước khi ghi log để không leak dữ liệu trong message lỗi.
def sanitize_exception_data(error: BaseException) -> dict[str, str]:
    return {
        "exception_type": type(error).__name__,
        "exception_message": sanitize_text(str(error)),
    }


# Nhận diện tên field/header có khả năng chứa credential hoặc token.
def _secret_key(key: str) -> bool:
    normalized = key.casefold().replace("-", "_")
    return normalized in {"authorization", "cookie", "password", "secret"} or any(
        part in normalized for part in ("api_key", "token", "service_key")
    )


# Thay UUID bằng placeholder tạm thời trong lúc sanitize text.
def _protect(value: str, protected: list[str]) -> str:
    protected.append(value)
    return f"\x00UUID{len(protected) - 1}\x00"


# Khôi phục UUID đã bảo vệ để log vẫn có định danh phục vụ trace/debug.
def _restore(value: str, protected: list[str]) -> str:
    for index, original in enumerate(protected):
        value = value.replace(f"\x00UUID{index}\x00", original)
    return value
