from __future__ import annotations

from pathlib import Path

from app.rag.vector_store import upsert_chunks

DOCS_DIR = Path(__file__).resolve().parents[2] / "docs"


# Chia tài liệu thành các đoạn có overlap nhỏ để giữ ngữ cảnh khi truy xuất.
def split_document(text: str, chunk_size: int = 900, overlap: int = 120) -> list[str]:
    normalized = "\n".join(line.rstrip() for line in text.splitlines()).strip()
    if not normalized:
        return []
    chunks: list[str] = []
    cursor = 0
    while cursor < len(normalized):
        end = min(cursor + chunk_size, len(normalized))
        chunks.append(normalized[cursor:end])
        if end == len(normalized):
            break
        cursor = max(end - overlap, cursor + 1)
    return chunks


# Đọc toàn bộ Markdown/TXT trong docs và seed các chunk kèm tên file nguồn.
async def seed_all_docs() -> dict:
    seeded_files: dict[str, int] = {}
    all_chunks: list[dict] = []
    for path in sorted(DOCS_DIR.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".md", ".txt"}:
            continue
        chunks = split_document(path.read_text(encoding="utf-8"))
        seeded_files[path.name] = len(chunks)
        all_chunks.extend({"source": path.name, "content": content} for content in chunks)
    total = await upsert_chunks(all_chunks)
    return {"seeded_files": seeded_files, "total_chunks": total}
