from dataclasses import dataclass

from app.rag.loader import Document


# ============================================================
# Chunk
# ============================================================
#
# Đây là cấu trúc dữ liệu đại diện cho MỘT đoạn nhỏ
# được chia ra từ Document.
#
# Ví dụ:
#
# README.md
#
#       ↓
#
# Document
#
#       ↓
#
# Chunk 0
# Chunk 1
# Chunk 2
#
# Mỗi Chunk giữ:
#
# - text
# - source
# - file_path
# - chunk_index
#
# source và file_path giúp chúng ta biết chunk này
# đến từ tài liệu nào.
#
# chunk_index giúp biết đây là chunk thứ mấy
# trong document gốc.
# ============================================================

@dataclass
class Chunk:
    text: str
    source: str
    file_path: str
    chunk_index: int


# ============================================================
# DocumentChunker
# ============================================================
#
# Class này chịu trách nhiệm duy nhất:
#
# Document
#     ↓
# chia thành các đoạn nhỏ
#     ↓
# list[Chunk]
#
# Nó KHÔNG làm:
#
# - đọc file
# - embedding
# - lưu Qdrant
# - retrieval
# - gọi LLM
# ============================================================

class DocumentChunker:

    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
    ) -> None:
        """
        Khởi tạo chunker.

        chunk_size:
            số ký tự tối đa trong một chunk.

        chunk_overlap:
            số ký tự được lặp lại giữa hai chunk liên tiếp.
        """

        # ----------------------------------------------------
        # 1. Validate chunk_size
        # ----------------------------------------------------

        if chunk_size <= 0:
            raise ValueError(
                "chunk_size must be greater than 0"
            )


        # ----------------------------------------------------
        # 2. Validate chunk_overlap
        # ----------------------------------------------------

        if chunk_overlap < 0:
            raise ValueError(
                "chunk_overlap cannot be negative"
            )


        # ----------------------------------------------------
        # 3. overlap phải nhỏ hơn chunk_size
        # ----------------------------------------------------
        #
        # Nếu:
        #
        # chunk_size = 1000
        # overlap    = 1000
        #
        # thì:
        #
        # step = 1000 - 1000
        #      = 0
        #
        # start không tăng
        # → infinite loop.
        # ----------------------------------------------------

        if chunk_overlap >= chunk_size:
            raise ValueError(
                "chunk_overlap must be smaller than chunk_size"
            )


        # ----------------------------------------------------
        # 4. Lưu config
        # ----------------------------------------------------

        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap


    def chunk_document(
        self,
        document: Document,
    ) -> list[Chunk]:
        """
        Chia một Document thành nhiều Chunk.

        Flow:

        Document
            ↓
        lấy document.text
            ↓
        sliding window
            ↓
        chunk text
            ↓
        tạo Chunk
            ↓
        list[Chunk]
        """

        # ----------------------------------------------------
        # 1. Lấy text từ Document
        # ----------------------------------------------------

        text = document.text


        # ----------------------------------------------------
        # 2. Defensive check
        # ----------------------------------------------------
        #
        # Loader hiện tại đã không cho file rỗng.
        #
        # Tuy nhiên Document có thể được tạo từ nơi khác,
        # vì vậy chunker vẫn kiểm tra.
        # ----------------------------------------------------

        if not text.strip():
            return []


        # ----------------------------------------------------
        # 3. List chứa kết quả
        # ----------------------------------------------------

        chunks: list[Chunk] = []


        # ----------------------------------------------------
        # 4. Vị trí bắt đầu chunk
        # ----------------------------------------------------

        start = 0


        # ----------------------------------------------------
        # 5. Index của chunk
        # ----------------------------------------------------

        chunk_index = 0


        # ----------------------------------------------------
        # 6. Sliding window
        # ----------------------------------------------------
        #
        # Loop tiếp tục cho tới khi start đi hết text.
        # ----------------------------------------------------

        while start < len(text):


            # ------------------------------------------------
            # 7. Tính vị trí kết thúc
            # ------------------------------------------------

            end = start + self.chunk_size


            # ------------------------------------------------
            # 8. Cắt text
            # ------------------------------------------------
            #
            # Ví dụ:
            #
            # start = 0
            # end   = 1000
            #
            # text[0:1000]
            # ------------------------------------------------

            chunk_text = text[start:end]


            # ------------------------------------------------
            # 9. Loại whitespace dư
            # ------------------------------------------------

            chunk_text = chunk_text.strip()


            # ------------------------------------------------
            # 10. Nếu chunk có nội dung thì tạo Chunk
            # ------------------------------------------------

            if chunk_text:

                chunk = Chunk(
                    text=chunk_text,
                    source=document.source,
                    file_path=document.file_path,
                    chunk_index=chunk_index,
                )


                # --------------------------------------------
                # Thêm Chunk vào kết quả
                # --------------------------------------------

                chunks.append(chunk)


                # --------------------------------------------
                # Tăng index cho chunk tiếp theo
                # --------------------------------------------

                chunk_index += 1


            # ------------------------------------------------
            # 11. Di chuyển sliding window
            # ------------------------------------------------
            #
            # Ví dụ:
            #
            # chunk_size    = 1000
            # chunk_overlap = 200
            #
            # step:
            #
            # 1000 - 200 = 800
            #
            # start:
            #
            # 0
            # 800
            # 1600
            # 2400
            # ...
            #
            # Nhờ vậy mỗi chunk overlap 200 ký tự
            # với chunk trước.
            # ------------------------------------------------

            start += self.chunk_size - self.chunk_overlap


        # ----------------------------------------------------
        # 12. Trả về toàn bộ chunks
        # ----------------------------------------------------

        return chunks


    def chunk_documents(
        self,
        documents: list[Document],
    ) -> list[Chunk]:
        """
        Chia nhiều Document thành một list Chunk.

        Flow:

        list[Document]
             ↓
        từng Document
             ↓
        chunk_document()
             ↓
        gộp tất cả chunk
             ↓
        list[Chunk]
        """

        # ----------------------------------------------------
        # 1. List chứa toàn bộ Chunk
        # ----------------------------------------------------

        chunks: list[Chunk] = []


        # ----------------------------------------------------
        # 2. Duyệt từng Document
        # ----------------------------------------------------

        for document in documents:


            # ------------------------------------------------
            # 3. Chunk document hiện tại
            # ------------------------------------------------

            document_chunks = self.chunk_document(
                document
            )


            # ------------------------------------------------
            # 4. Gộp vào list chung
            # ------------------------------------------------
            #
            # Dùng extend thay vì append.
            #
            # document_chunks:
            #
            # [
            #     Chunk(...),
            #     Chunk(...),
            # ]
            #
            # extend:
            #
            # chunks = [
            #     Chunk(...),
            #     Chunk(...),
            # ]
            #
            # append sẽ tạo list lồng nhau:
            #
            # [
            #     [
            #         Chunk(...),
            #         Chunk(...),
            #     ]
            # ]
            # ------------------------------------------------

            chunks.extend(document_chunks)


        # ----------------------------------------------------
        # 5. Return
        # ----------------------------------------------------

        return chunks