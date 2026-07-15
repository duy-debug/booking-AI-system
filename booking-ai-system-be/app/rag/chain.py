# RAG chain: retrieve context → call Groq → trả lời streaming
# Dùng OpenAI SDK với base_url trỏ đến Groq API

from openai import OpenAI

from app.core.config import settings
from app.rag.embeddings import embed_text
from app.rag.prompts import SYSTEM_PROMPT
from app.rag.vector_store import search_similar


def _get_groq_client() -> OpenAI:
    # Khởi tạo OpenAI SDK nhưng trỏ về Groq
    if not settings.GROQ_API_KEY or settings.GROQ_API_KEY == "gsk_...":
        raise RuntimeError(
            "GROQ_API_KEY chưa được cấu hình. "
            "Đăng ký tại https://console.groq.com và thêm vào .env"
        )
    return OpenAI(
        api_key=settings.GROQ_API_KEY,
        base_url=settings.GROQ_BASE_URL,
    )


def _retrieve_context(db, query: str, top_k: int = 3) -> list[str]:
    # Embed câu hỏi → search pgvector → trả list content chunks
    query_vec = embed_text(query)
    chunks = search_similar(db, query_vec, top_k=top_k)
    return [c.content for c in chunks]


def generate_response(db, query: str, top_k: int = 3) -> str:
    # RAG chain đồng bộ: retrieve → build prompt → call Groq → trả string
    contexts = _retrieve_context(db, query, top_k=top_k)
    context_text = "\n\n---\n\n".join(contexts)

    prompt = SYSTEM_PROMPT.format(context=context_text)

    client = _get_groq_client()
    resp = client.chat.completions.create(
        model=settings.GROQ_MODEL,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": query},
        ],
        temperature=0.3,
        max_tokens=1024,
    )

    return resp.choices[0].message.content


def generate_stream(db, query: str, top_k: int = 3):
    # RAG chain streaming: yield từng chunk text từ Groq
    contexts = _retrieve_context(db, query, top_k=top_k)
    context_text = "\n\n---\n\n".join(contexts)

    prompt = SYSTEM_PROMPT.format(context=context_text)

    client = _get_groq_client()
    stream = client.chat.completions.create(
        model=settings.GROQ_MODEL,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": query},
        ],
        temperature=0.3,
        max_tokens=1024,
        stream=True,
    )

    for chunk in stream:
        delta = chunk.choices[0].delta
        if delta and delta.content:
            yield delta.content
