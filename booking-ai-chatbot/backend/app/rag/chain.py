from __future__ import annotations

import asyncio
from typing import Any

from app.core.config import settings
from app.core.exceptions import AppError
from app.integrations import groq as groq_integration
from app.rag.prompts import build_grounded_prompt
from app.rag.vector_store import search_chunks


# Lấy Groq adapter tại thời điểm gọi để lifecycle và test có thể thay thế dependency.
def get_groq_client() -> Any:
    return groq_integration.get_groq_client()


# Truy xuất context trước, sau đó dùng LLM chỉ để diễn đạt câu trả lời đã grounded.
async def answer_faq(query: str) -> str:
    chunks = await search_chunks(query)
    if not chunks:
        return "Tôi chưa tìm thấy thông tin phù hợp trong kho kiến thức."
    client = get_groq_client()
    messages = [
        {"role": "system", "content": build_grounded_prompt(chunks)},
        {"role": "user", "content": query},
    ]

    # Chạy OpenAI-compatible SDK đồng bộ trên worker thread để không chặn event loop.
    def _complete() -> Any:
        return client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=messages,
            temperature=0,
        )

    try:
        response = await asyncio.to_thread(_complete)
    except Exception as exc:
        raise AppError(
            503,
            code="LLM_UNAVAILABLE",
            detail="Dịch vụ AI đang tạm thời không khả dụng.",
        ) from exc
    return str(response.choices[0].message.content or "").strip()
