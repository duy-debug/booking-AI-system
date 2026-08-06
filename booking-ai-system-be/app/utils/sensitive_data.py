"""Central masking and redaction for POS observability."""

import re
from collections.abc import Mapping

_PHONE = re.compile(r"(?<!\d)\+?\d(?:[ -]?\d){8,14}(?!\d)")
_EMAIL = re.compile(r"\b([^\s@])[^\s@]*@([^\s@]+)\b")
_BEARER = re.compile(r"(?i)\bBearer\s+[^\s,;]+")
_UUID = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)


def mask_phone(value: str) -> str:
    digits = "".join(character for character in value if character.isdigit())
    return f"{digits[:3]}***{digits[-4:]}" if len(digits) >= 7 else "***"


def mask_email(value: str) -> str:
    match = _EMAIL.fullmatch(value.strip())
    return f"{match.group(1)}***@{match.group(2)}" if match else "***"


def redact_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {
        key: "***" if _secret_key(key) else sanitize_text(value)
        for key, value in headers.items()
    }


def sanitize_dict(values: Mapping[str, object]) -> dict[str, object]:
    return {str(key): sanitize_value(str(key), value) for key, value in values.items()}


def sanitize_value(key: str, value: object) -> object:
    normalized = key.casefold().replace("-", "_")
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
    if isinstance(value, list | tuple | set | frozenset):
        return [sanitize_value(key, item) for item in value]
    if value is None or isinstance(value, bool | int | float):
        return value
    return str(value)


def sanitize_text(value: str) -> str:
    protected: list[str] = []
    sanitized = _UUID.sub(lambda match: _protect(match.group(0), protected), value)
    sanitized = _BEARER.sub("Bearer ***", sanitized)
    sanitized = _PHONE.sub(lambda match: mask_phone(match.group(0)), sanitized)
    sanitized = _EMAIL.sub(
        lambda match: f"{match.group(1)}***@{match.group(2)}", sanitized
    )
    return _restore(sanitized, protected)


def sanitize_exception_data(error: BaseException) -> dict[str, str]:
    return {
        "exception_type": type(error).__name__,
        "exception_message": sanitize_text(str(error)),
    }


def _secret_key(key: str) -> bool:
    normalized = key.casefold().replace("-", "_")
    return normalized in {"authorization", "cookie", "password", "secret"} or any(
        part in normalized for part in ("api_key", "token", "service_key")
    )


def _protect(value: str, protected: list[str]) -> str:
    protected.append(value)
    return f"\x00UUID{len(protected) - 1}\x00"


def _restore(value: str, protected: list[str]) -> str:
    for index, original in enumerate(protected):
        value = value.replace(f"\x00UUID{index}\x00", original)
    return value
