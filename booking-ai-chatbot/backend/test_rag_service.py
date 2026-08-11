import asyncio
import os

from dotenv import load_dotenv

from app.rag.embedding import EmbeddingModel
from app.rag.prompt import PromptBuilder
from app.rag.reranker import Reranker
from app.rag.retriever import Retriever
from app.rag.service import RAGService
from app.rag.vector_store import VectorStore


load_dotenv()
async def main() -> None:

    # ========================================================
    # STEP 1: Mở Qdrant local store
    # ========================================================

    store = VectorStore()


    # ========================================================
    # STEP 2: Tạo embedding model
    # ========================================================

    embedder = EmbeddingModel()


    # ========================================================
    # STEP 3: Tạo Retriever
    # ========================================================

    retriever = Retriever(
        embedder=embedder,
        vector_store=store,
    )


    # ========================================================
    # STEP 4: Tạo Reranker
    # ========================================================

    reranker = Reranker()


    # ========================================================
    # STEP 5: Tạo PromptBuilder
    # ========================================================

    prompt_builder = PromptBuilder()


    # ========================================================
    # STEP 6: Tạo RAGService
    # ========================================================
    #
    # Gemini config lấy từ environment variables.
    #
    # Không hard-code API key vào source code.
    #
    # ========================================================

    rag_service = RAGService(
        retriever=retriever,
        reranker=reranker,
        prompt_builder=prompt_builder,
        api_key=os.getenv(
            "GEMINI_API_KEY",
            "",
        ),
        base_url=os.getenv(
            "GEMINI_BASE_URL",
            "",
        ),
        model=os.getenv(
            "GEMINI_MODEL",
            "",
        ),
        fallback_model=os.getenv(
            "GEMINI_FALLBACK_MODEL",
        ),
        max_retries=int(
            os.getenv(
                "LLM_MAX_RETRIES",
                "0",
            )
        ),
    )


    try:

        # ====================================================
        # STEP 7: Gửi query vào RAG pipeline
        # ====================================================

        answer = await rag_service.answer(
            query="RAG là gì?",
            retrieve_top_k=10,
            rerank_top_n=3,
        )


        # ====================================================
        # STEP 8: Print final answer
        # ====================================================

        print("\n===== RAG ANSWER =====\n")
        print(answer)


    finally:

        # ====================================================
        # STEP 9: Cleanup
        # ====================================================
        #
        # VectorStore dùng Qdrant local
        # → cần close.
        #
        # RAGService tự tạo HTTP client
        # → cũng cần close.
        #
        # ====================================================

        store.close()
        await rag_service.close()


if __name__ == "__main__":
    asyncio.run(main())