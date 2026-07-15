# Thao tác với kb_chunks trên pgvector — insert + search + delete

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.models.knowledge_chunk import KnowledgeChunk


def insert_chunk(
    db: Session,
    source: str,
    content: str,
    embedding: list[float],
    chunk_order: int | None = None,
) -> KnowledgeChunk:
    # Tạo mới một chunk trong kb_chunks
    chunk = KnowledgeChunk(
        source=source,
        content=content,
        embedding=embedding,
        chunk_order=chunk_order,
    )
    db.add(chunk)
    db.commit()
    db.refresh(chunk)
    return chunk


def search_similar(
    db: Session,
    query_embedding: list[float],
    top_k: int = 5,
    source_filter: str | None = None,
) -> list[KnowledgeChunk]:
    # Cosine similarity search trên pgvector (IVFFlat index)
    # Dùng toán tử <=> (cosine distance) vì embedding đã normalize
    # Chuyển list[float] → string '[0.1,0.2,...]' cho pgvector
    vec_str = "[" + ",".join(str(v) for v in query_embedding) + "]"

    sql = """
        SELECT chunk_id, source, content, chunk_order,
               1 - (embedding <=> CAST(:query_vec AS vector)) AS similarity
        FROM kb_chunks
        WHERE embedding IS NOT NULL
    """
    params: dict = {"query_vec": vec_str, "top_k": top_k}

    if source_filter:
        sql += " AND source = :source"
        params["source"] = source_filter

    sql += " ORDER BY embedding <=> CAST(:query_vec AS vector) LIMIT :top_k"

    rows = db.execute(text(sql), params).fetchall()

    # Map kết quả về list KnowledgeChunk
    results = []
    for row in rows:
        chunk = (
            db.query(KnowledgeChunk)
            .filter(KnowledgeChunk.chunk_id == row[0])
            .first()
        )
        if chunk:
            results.append(chunk)
    return results


def delete_all_chunks(db: Session, source: str | None = None) -> int:
    # Xoá toàn bộ chunks — dùng khi seed lại KB
    q = db.query(KnowledgeChunk)
    if source:
        q = q.filter(KnowledgeChunk.source == source)
    deleted = q.delete(synchronize_session=False)
    db.commit()
    return deleted


def count_chunks(db: Session, source: str | None = None) -> int:
    # Đếm số chunks (có thể filter theo source)
    q = db.query(KnowledgeChunk)
    if source:
        q = q.filter(KnowledgeChunk.source == source)
    return q.count()
