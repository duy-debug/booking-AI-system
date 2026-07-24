from __future__ import annotations

import re
import unicodedata

from app.domain.intent import Intent


# Chuẩn hóa tiếng Việt về chữ thường không dấu để phân loại ổn định hơn.
def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.lower())
    without_marks = "".join(
        character for character in decomposed if unicodedata.category(character) != "Mn"
    )
    normalized = without_marks.replace("đ", "d")
    return re.sub(r"\s+", " ", normalized).strip()


# Phân loại nhanh các intent rõ ràng; LLM structured output có thể thay thế ở bước sau.
def classify_query(query: str) -> str:
    text = _normalize(query)
    rules = (
        (Intent.FAQ, ("chinh sach", "quy trinh", "lam the nao", "faq")),
        (Intent.CANCEL_BOOKING, ("huy lich", "cancel")),
        (Intent.UPDATE_BOOKING, ("doi lich", "sua lich", "reschedule")),
        (Intent.LOOKUP_BOOKING, ("tra cuu", "lich da dat", "booking cua toi")),
        (Intent.CHECK_SLOT, ("slot", "khung gio", "con trong")),
        (Intent.CREATE_BOOKING, ("dat lich", "dat cho", "book lich")),
        (Intent.SHOP_INFO, ("chi nhanh", "cua hang", "dia chi")),
        (Intent.COURSE_INFO, ("dich vu", "massage nao", "goi nao", "course")),
    )
    for intent, keywords in rules:
        if any(keyword in text for keyword in keywords):
            return intent.value
    if any(word in text for word in ("xin chao", "hello", "chao ban")):
        return Intent.GENERAL.value
    return Intent.FAQ.value
