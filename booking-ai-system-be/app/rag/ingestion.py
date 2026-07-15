# Ingest tài liệu từ docs/ vào kb_chunks — chunk + embed + insert
# Chạy: POST /api/kb/seed (admin) hoặc gọi hàm này từ CLI

import os
from pathlib import Path

from sqlalchemy.orm import Session

from app.rag.embeddings import embed_texts
from app.rag.vector_store import delete_all_chunks, insert_chunk

# Đường dẫn đến thư mục docs (từ thư mục backend)
DOCS_DIR = Path(__file__).resolve().parents[3] / "docs"

# Chunk size: ~500 ký tự, overlap ~50 ký tự
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50


def _chunk_text(text: str, source: str) -> list[dict]:
    # Chia text thành các chunks nhỏ, có overlap
    lines = text.split("\n")
    chunks = []
    current_chunk = ""
    chunk_order = 0

    for line in lines:
        # Giữ nguyên header lines (##, ###) làm mốc
        if not current_chunk:
            current_chunk = line
        elif len(current_chunk) + len(line) + 1 <= CHUNK_SIZE:
            current_chunk += "\n" + line
        else:
            # Lưu chunk hiện tại
            chunks.append({
                "source": source,
                "content": current_chunk.strip(),
                "chunk_order": chunk_order,
            })
            chunk_order += 1
            # Overlap: lấy 50 ký tự cuối của chunk cũ làm đầu chunk mới
            if CHUNK_OVERLAP > 0 and len(current_chunk) > CHUNK_OVERLAP:
                # Tìm dòng mới gần nhất trong overlap region
                overlap_start = max(
                    current_chunk.rfind("\n", -CHUNK_OVERLAP * 2),
                    len(current_chunk) - CHUNK_OVERLAP,
                )
                current_chunk = current_chunk[overlap_start:].strip() + "\n" + line
            else:
                current_chunk = line

    # Chunk cuối cùng
    if current_chunk.strip():
        chunks.append({
            "source": source,
            "content": current_chunk.strip(),
            "chunk_order": chunk_order,
        })

    return chunks


def seed_all_docs(db: Session) -> dict:
    # Xoá dữ liệu cũ, đọc tất cả file .md trong docs/, chunk + embed + insert
    md_files = sorted(DOCS_DIR.glob("*.md"))

    if not md_files:
        # Fallback: thử tìm docs ở vị trí khác (cạnh backend)
        alt_docs = Path(__file__).resolve().parents[2] / "docs"
        if alt_docs.exists():
            md_files = sorted(alt_docs.glob("*.md"))

    stats: dict[str, int] = {}

    for md_file in md_files:
        source = md_file.name
        text = md_file.read_text(encoding="utf-8")
        chunks = _chunk_text(text, source)

        if not chunks:
            continue

        # Nhúng batch toàn bộ chunks của file
        contents = [c["content"] for c in chunks]
        embeddings = embed_texts(contents)

        # Insert từng chunk
        for i, chunk_data in enumerate(chunks):
            insert_chunk(
                db=db,
                source=chunk_data["source"],
                content=chunk_data["content"],
                embedding=embeddings[i],
                chunk_order=chunk_data["chunk_order"],
            )

        stats[source] = len(chunks)

    return {"seeded_files": stats, "total_chunks": sum(stats.values())}
