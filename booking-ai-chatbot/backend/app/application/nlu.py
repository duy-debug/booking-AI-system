from __future__ import annotations

import re
from datetime import timedelta

from app.core.business_time import business_today
from app.domain.intent import Intent
from app.domain.nlu import NLUResult
from app.tools.intent import classify_query, normalize_text

RESOURCE_BY_INTENT = {
    Intent.SHOP_INFO: ("shop", "list"),
    Intent.COURSE_INFO: ("course", "list"),
    Intent.CHECK_SLOT: ("slot", "check"),
    Intent.CREATE_BOOKING: ("booking", "create"),
    Intent.UPDATE_BOOKING: ("booking", "update"),
    Intent.CANCEL_BOOKING: ("booking", "cancel"),
    Intent.LOOKUP_BOOKING: ("booking", "lookup"),
    Intent.FAQ: ("knowledge", "search"),
    Intent.GENERAL: ("conversation", "respond"),
}


class StructuredNLU:
    # Phân tích câu nói thành intent/resource/operation/entities mà không gọi tool.
    async def parse(self, query: str) -> NLUResult:
        intent = Intent(classify_query(query))
        resource, operation = RESOURCE_BY_INTENT.get(intent, (None, None))
        return NLUResult(
            intent=intent,
            resource=resource,
            operation=operation,
            entities=self._extract_entities(query),
        )

    # Trích xuất các entity có định dạng chắc chắn; giá trị mơ hồ được để thiếu.
    @staticmethod
    def _extract_entities(query: str) -> dict[str, str]:
        entities: dict[str, str] = {}
        normalized_query = normalize_text(query)
        phone = re.search(r"(?<!\d)(0\d{9,10})(?!\d)", query)
        iso_date = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", query)
        clock = re.search(
            r"\b([01]?\d|2[0-3])(?:\s*[:h]\s*(\d{2})?|\s+gio)\b",
            normalized_query,
        )
        booking_id = re.search(
            r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-"
            r"[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\b",
            query,
        )
        booking_code = re.search(r"\b(?:BK|RES)[A-Z0-9-]+\b", query.upper())
        if phone:
            entities["phone"] = phone.group(1)
        if iso_date:
            entities["booking_date"] = iso_date.group(1)
        elif "ngay kia" in normalized_query:
            entities["booking_date"] = (business_today() + timedelta(days=2)).isoformat()
        elif "ngay mai" in normalized_query:
            entities["booking_date"] = (business_today() + timedelta(days=1)).isoformat()
        elif "hom nay" in normalized_query:
            entities["booking_date"] = business_today().isoformat()
        if clock:
            entities["start_time"] = f"{int(clock.group(1)):02d}:{clock.group(2) or '00'}"
        if booking_id:
            entities["booking_id"] = booking_id.group(0).lower()
        if booking_code:
            entities["booking_code"] = booking_code.group(0)
        return entities
