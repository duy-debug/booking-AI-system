from app.rag.reranker import RerankedResult


# ============================================================
# PromptBuilder
# ============================================================
#
# Class này chịu trách nhiệm:
#
# user query
#     +
# reranked context
#     ↓
# prompt hoàn chỉnh cho LLM
#
# Nó KHÔNG:
#
# - retrieve
# - rerank
# - embedding
# - gọi LLM
# - lưu Qdrant
#
# ============================================================

class PromptBuilder:

    def build(
        self,
        query: str,
        results: list[RerankedResult],
    ) -> str:
        """
        Build prompt cho LLM từ:
        - user query
        - các context đã được rerank
        """

        # ----------------------------------------------------
        # 1. Validate query
        # ----------------------------------------------------

        if not query.strip():
            raise ValueError(
                "Query cannot be empty"
            )


        # ----------------------------------------------------
        # 2. Validate context
        # ----------------------------------------------------
        #
        # Nếu không retrieve/rerank được context nào,
        # vẫn có thể build prompt nhưng nên nói rõ
        # là không có context.
        # ----------------------------------------------------

        if not results:
            context = "Không có context phù hợp được tìm thấy."

        else:

            # ------------------------------------------------
            # 3. Build từng context
            # ------------------------------------------------

            context_parts: list[str] = []

            for index, result in enumerate(
                results,
                start=1,
            ):

                context_parts.append(
                    f"[Context {index}]\n"
                    f"Source: {result.source}\n"
                    f"Chunk: {result.chunk_index}\n"
                    f"Content:\n{result.text}"
                )


            # ------------------------------------------------
            # 4. Ghép tất cả context
            # ------------------------------------------------

            context = "\n\n".join(
                context_parts
            )


        # ----------------------------------------------------
        # 5. Build final prompt
        # ----------------------------------------------------

        prompt = f"""
Vai trò: trợ lý hỏi đáp dựa trên tài liệu.

Nhiệm vụ:
Trả lời câu hỏi của người dùng chỉ dựa trên CONTEXT được cung cấp bên dưới.

Quy tắc:
- Không tự bịa hoặc thêm thông tin không có trong CONTEXT.
- Nếu CONTEXT không đủ để trả lời, hãy nói rõ rằng không tìm thấy đủ thông tin trong tài liệu.
- Trả lời rõ ràng, chính xác và ngắn gọn.
- Ưu tiên thông tin liên quan trực tiếp đến câu hỏi.
- Nếu sử dụng thông tin từ tài liệu, hãy nêu tên nguồn khi phù hợp.
- Không đề cập đến retrieval score hoặc rerank score trong câu trả lời.

CONTEXT:
{context}

QUESTION:
{query}

ANSWER:
""".strip()

        return prompt
