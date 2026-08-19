"""Adapter để embedding của app dùng được với LlamaIndex."""

from importlib import import_module

from app.knowledge.embeddings.sentence_transformer import SentenceTransformerEmbedding


def build_llamaindex_embedding(embedding: SentenceTransformerEmbedding) -> object:
    """Adapter sentence-transformer gateway hiện có sang LlamaIndex."""
    # ----------------------------------------------------
    # STEP 1: Import LlamaIndex/Pydantic khi thật sự cần
    # ----------------------------------------------------
    #
    # Runtime bình thường vẫn dùng app-owned embedding. Chỉ khi bật
    # LlamaIndex indexing/retrieval thì mới cần import các dependency này.
    # ----------------------------------------------------
    embeddings_module = import_module("llama_index.core.embeddings")
    pydantic_module = import_module("pydantic")
    base_embedding = getattr(embeddings_module, "BaseEmbedding")
    private_attr = getattr(pydantic_module, "PrivateAttr")

    class SentenceTransformerLlamaIndexEmbedding(base_embedding):
        _embedding: SentenceTransformerEmbedding = private_attr()

        def __init__(self, wrapped: SentenceTransformerEmbedding) -> None:
            # ------------------------------------------------
            # STEP 2: Bọc embedding hiện có vào BaseEmbedding của LlamaIndex
            # ------------------------------------------------
            #
            # LlamaIndex cần object kế thừa BaseEmbedding, còn app đang có
            # SentenceTransformerEmbedding riêng để dễ test và tái sử dụng.
            # ------------------------------------------------
            super().__init__(model_name=wrapped.model_name)
            self._embedding = wrapped

        def _get_query_embedding(self, query: str) -> list[float]:
            # ------------------------------------------------
            # STEP 3: Ánh xạ query embedding sync
            # ------------------------------------------------
            #
            # LlamaIndex gọi method này khi cần embed câu hỏi lúc retrieval.
            # ------------------------------------------------
            return self._embedding.embed_query(query)

        def _get_text_embedding(self, text: str) -> list[float]:
            # ------------------------------------------------
            # STEP 4: Ánh xạ text embedding sync
            # ------------------------------------------------
            #
            # Dùng cùng batch API với một phần tử để output đồng nhất với
            # embed_documents().
            # ------------------------------------------------
            return self._embedding.embed_documents((text,))[0]

        def _get_text_embeddings(self, texts: list[str]) -> list[list[float]]:
            # ------------------------------------------------
            # STEP 5: Ánh xạ batch text embedding sync
            # ------------------------------------------------
            #
            # LlamaIndex dùng method này khi insert nhiều TextNode.
            # ------------------------------------------------
            return self._embedding.embed_documents(texts)

        async def _aget_query_embedding(self, query: str) -> list[float]:
            # ------------------------------------------------
            # STEP 6: Ánh xạ query embedding async
            # ------------------------------------------------
            #
            # Model local vẫn chạy sync; async method chỉ đáp ứng interface
            # của LlamaIndex.
            # ------------------------------------------------
            return self._get_query_embedding(query)

        async def _aget_text_embedding(self, text: str) -> list[float]:
            # ------------------------------------------------
            # STEP 7: Ánh xạ text embedding async
            # ------------------------------------------------
            #
            # Giữ cùng logic với sync path để tránh lệch kết quả embedding.
            # ------------------------------------------------
            return self._get_text_embedding(text)

    # ----------------------------------------------------
    # STEP 8: Trả adapter cho LlamaIndex
    # ----------------------------------------------------
    #
    # Từ đây VectorStoreIndex có thể dùng embedding của app như một
    # LlamaIndex embed model bình thường.
    # ----------------------------------------------------
    return SentenceTransformerLlamaIndexEmbedding(embedding)
