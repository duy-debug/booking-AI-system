from app.rag_v1.vector_store import SearchResult

# ============================================================
# RRF Fusion
# ============================================================
#
# File này chịu trách nhiệm GỘP kết quả search.
#
# RRF = Reciprocal Rank Fusion.
#
# Ý tưởng:
#
# - semantic search có một danh sách rank riêng
# - keyword search có một danh sách rank riêng
# - RRF cộng điểm theo vị trí rank
# - document xuất hiện cao ở nhiều danh sách sẽ được ưu tiên
#
# ============================================================


def rrf_merge(
    semantic_results: list[SearchResult],
    keyword_results: list[SearchResult],
    limit: int,
    rank_constant: int = 60,
) -> list[SearchResult]:
    """
    Gộp semantic results và keyword results bằng RRF.

    Flow:

    semantic top-k
         ↓
    keyword top-k
         ↓
    cộng điểm theo công thức 1 / (rank_constant + rank)
         ↓
    sort lại
         ↓
    top-k cuối cùng
    """

    # ----------------------------------------------------
    # 1. Validate input
    # ----------------------------------------------------

    if limit <= 0:
        raise ValueError(
            "limit must be greater than 0"
        )

    if rank_constant <= 0:
        raise ValueError(
            "rank_constant must be greater than 0"
        )


    # ----------------------------------------------------
    # 2. Cộng điểm RRF theo từng danh sách rank
    # ----------------------------------------------------

    merged_results: dict[tuple[str, str, int], SearchResult] = {}
    merged_scores: dict[tuple[str, str, int], float] = {}

    for results in (
        semantic_results,
        keyword_results,
    ):
        for rank, result in enumerate(
            results,
            start=1,
        ):
            key = (
                result.source,
                result.file_path,
                result.chunk_index,
            )

            if key not in merged_results:
                merged_results[key] = result
                merged_scores[key] = 0.0

            merged_scores[key] += 1 / (
                rank_constant
                + rank
            )


    # ----------------------------------------------------
    # 3. Trả về SearchResult với score là RRF score
    # ----------------------------------------------------

    fused_results = [
        SearchResult(
            text=result.text,
            source=result.source,
            file_path=result.file_path,
            chunk_index=result.chunk_index,
            score=merged_scores[key],
        )
        for key, result in merged_results.items()
    ]

    fused_results.sort(
        key=lambda item: item.score,
        reverse=True,
    )

    return fused_results[:limit]
