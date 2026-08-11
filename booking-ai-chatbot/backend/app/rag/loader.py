
from dataclasses import dataclass
from pathlib import Path
# ============================================================
# Document
# ============================================================
# Đây là cấu trúc dữ liệu đại diện cho MỘT tài liệu sau khi load.
#
# Ví dụ:
#
# booking_policy.md
#        ↓
# Document(
#     text="Nội dung chính sách...",
#     source="booking_policy.md",
#     file_path="knowledge/booking_policy.md"
# )
#
# Ở bước loader:
# - text      = toàn bộ nội dung file
# - source    = tên file
# - file_path = đường dẫn file
#
# Sau này chunker.py sẽ nhận Document này và chia nó
# thành nhiều chunk nhỏ hơn.
# ============================================================
@dataclass
class Document:
    text: str
    source: str
    file_path: str

# ============================================================
# DocumentLoader
# ============================================================
# Class này chịu trách nhiệm duy nhất:
#
#     File / Folder
#          ↓
#     đọc nội dung
#          ↓
#       Document
#
# Nó KHÔNG làm:
# - chunking
# - embedding
# - lưu Qdrant
# - retrieval
# ============================================================

class DocumentLoader:
    # Các loại file mà loader hiện tại cho phép đọc.
    #
    # Ban đầu chỉ hỗ trợ .md và .txt để flow đơn giản,
    # dễ debug và dễ hiểu.
    #
    # Sau này có thể mở rộng:
    # .pdf
    # .docx
    # .html
    SUPPORTED_EXTENSIONS = {".md", ".txt"}

    def load_file(self, file_path: str | Path) -> Document:
        """
        Load một file text và chuyển thành Document.

        Flow:

        file_path
            ↓
        kiểm tra file tồn tại
            ↓
        kiểm tra extension
            ↓
        đọc UTF-8
            ↓
        tạo Document
            ↓
        return
        """

        # ----------------------------------------------------
        # 1. Chuyển input thành Path object
        # ----------------------------------------------------
        # Người gọi có thể truyền:
        #
        # "knowledge/booking_policy.md"
        #
        # hoặc:
        #
        # Path("knowledge/booking_policy.md")
        #
        # Chuyển hết về Path giúp thao tác filesystem rõ hơn.
        # ----------------------------------------------------

        path = Path(file_path)

        # ----------------------------------------------------
        # 2. Kiểm tra file có tồn tại hay không
        # ----------------------------------------------------

        if not path.exists():
            raise FileNotFoundError(
                f"Knowledge file does not exist: {path}"
            )


        # ----------------------------------------------------
        # 3. Kiểm tra đây có thật sự là file không
        # ----------------------------------------------------

        if not path.is_file():
            raise ValueError(
                f"Path is not a file: {path}"
            )


        # ----------------------------------------------------
        # 4. Kiểm tra loại file có được hỗ trợ không
        # ----------------------------------------------------
        #
        # path.suffix:
        #
        # booking_policy.md
        #                 ↓
        #                ".md"
        #
        # lower() giúp:
        #
        # POLICY.MD
        #
        # vẫn được nhận dạng là .md.
        # ----------------------------------------------------

        extension = path.suffix.lower()

        if extension not in self.SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Unsupported file type: {extension}"
            )


        # ----------------------------------------------------
        # 5. Đọc toàn bộ nội dung file
        # ----------------------------------------------------
        #
        # encoding="utf-8" rất quan trọng với knowledge
        # tiếng Việt.
        #
        # pathlib.Path.read_text() tự mở file, đọc nội dung
        # rồi đóng file sau khi hoàn tất.
        # ----------------------------------------------------

        text = path.read_text(encoding="utf-8")


        # ----------------------------------------------------
        # 6. Kiểm tra file có nội dung hay không
        # ----------------------------------------------------
        #
        # strip() loại bỏ khoảng trắng / newline ở đầu cuối.
        #
        # Ví dụ:
        #
        # "\n\n   \n"
        #
        # sau strip() sẽ trở thành:
        #
        # ""
        # ----------------------------------------------------

        if not text.strip():
            raise ValueError(
                f"Knowledge file is empty: {path}"
            )


        # ----------------------------------------------------
        # 7. Tạo Document
        # ----------------------------------------------------
        #
        # Tại đây chúng ta GIỮ NGUYÊN toàn bộ document.
        #
        # Chưa chia chunk.
        #
        # Ví dụ:
        #
        # booking_policy.md
        #
        # → 1 Document
        #
        # Sau này chunker.py:
        #
        # 1 Document
        #    ↓
        # chunk 1
        # chunk 2
        # chunk 3...
        # ----------------------------------------------------

        return Document(
            text=text,
            source=path.name,
            file_path=str(path),
        )


    def load_directory(
        self,
        directory_path: str | Path,
    ) -> list[Document]:
        """
        Load tất cả file knowledge được hỗ trợ trong một folder.

        Flow:

        knowledge/
            ├── a.md
            ├── b.md
            └── c.txt

                 ↓

        load_directory()

                 ↓

        [
            Document(a),
            Document(b),
            Document(c)
        ]
        """

        directory = Path(directory_path)


        # ----------------------------------------------------
        # 1. Kiểm tra directory tồn tại
        # ----------------------------------------------------

        if not directory.exists():
            raise FileNotFoundError(
                f"Knowledge directory does not exist: {directory}"
            )


        # ----------------------------------------------------
        # 2. Kiểm tra path có phải folder không
        # ----------------------------------------------------

        if not directory.is_dir():
            raise ValueError(
                f"Path is not a directory: {directory}"
            )


        documents: list[Document] = [] # khởi tạo đây là một list rỗng để chứa tất cả objects Document sau khi load.


        # ----------------------------------------------------
        # 3. Duyệt từng item trong folder
        # ----------------------------------------------------
        #
        # sorted() giúp thứ tự load ổn định.
        #
        # Điều này rất hữu ích khi debug:
        # mỗi lần chạy sẽ load theo cùng thứ tự.
        # ----------------------------------------------------

        for path in sorted(directory.iterdir()):

            # Folder con hoặc các file khác sẽ bỏ qua.
            if not path.is_file():
                continue

            # Chỉ lấy extension được hỗ trợ.
            if path.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
                continue


            # ------------------------------------------------
            # 4. Tái sử dụng load_file()
            # ------------------------------------------------
            #
            # Không duplicate logic đọc file ở đây.
            #
            # load_directory chỉ orchestration.
            # load_file mới chịu trách nhiệm load một file.
            # ------------------------------------------------

            document = self.load_file(path)

            documents.append(document)


        return documents