from pathlib import Path
import uuid

from fastapi import HTTPException, UploadFile, status

from app.core.config import settings
from app.models.document import Document, DocumentChunk, ProcessingStatus
from app.repositories.document_repo import DocumentRepository
from app.repositories.tag_repo import TagRepository
from app.utils.text_extract import chunk_text, embed_text, extract_text, make_summary

ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "txt", "pptx", "jpg", "jpeg", "png"}


class DocumentService:

    def __init__(self, doc_repo: DocumentRepository, tag_repo: TagRepository):
        self.doc_repo = doc_repo
        self.tag_repo = tag_repo

    def save_upload(
        self,
        file: UploadFile,
        title: str | None,
        folder_id: uuid.UUID | None,
        uploaded_by: uuid.UUID,
        tags: list[str] | None = None,
    ) -> Document:
        filename = file.filename or ""
        ext = Path(filename).suffix.lower().lstrip(".")

        # 1. Validate định dạng file
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Định dạng file .{ext} không được hỗ trợ.",
            )

        # 2. Tạo thư mục & Đọc file
        upload_dir = Path(settings.UPLOAD_DIR)
        upload_dir.mkdir(parents=True, exist_ok=True)

        content = file.file.read()
        if len(content) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="File vượt quá dung lượng cho phép.",
            )

        # 3. Ghi file vào đĩa
        stored_name = f"{uuid.uuid4().hex}.{ext}"
        file_path = upload_dir / stored_name
        file_path.write_bytes(content)

        # 4. Lưu Metadata Document vào DB (Trạng thái PENDING)
        doc_title = title if title else (filename or "Untitled Document")
        document = Document(
            title=doc_title,
            file_path=str(file_path),
            file_type=ext,
            folder_id=folder_id,
            uploaded_by=uploaded_by,
            processing_status=ProcessingStatus.PENDING,
        )
        document = self.doc_repo.create(document)

        # 5. Gán Tags (tận dụng TagRepository)
        if tags:
            for tag_name in tags:
                clean_tag = tag_name.strip()
                if clean_tag:
                    tag = self.tag_repo.get_or_create(clean_tag)
                    self.tag_repo.attach_to_document(document.id, tag.id)

        return document

    def process_document_sync(self, document_id: uuid.UUID) -> None:
        """Chạy ngầm (Worker task): Extract text -> Chunk -> Embed -> Summarize."""
        document = self.doc_repo.get_by_id(document_id)
        if not document:
            return

        self.doc_repo.update_status(document, ProcessingStatus.PROCESSING)

        try:
            text = extract_text(document.file_path, document.file_type)
            chunks = chunk_text(text)

            chunk_rows = [
                DocumentChunk(
                    document_id=document.id,
                    chunk_index=i,
                    content=chunk,
                    embedding=embed_text(chunk),
                )
                for i, chunk in enumerate(chunks)
            ]

            if chunk_rows:
                self.doc_repo.add_chunks(chunk_rows)

            summary = make_summary(text)
            self.doc_repo.update_status(
                document, ProcessingStatus.DONE, summary=summary
            )

        except Exception as e:
            # Cập nhật trạng thái FAILED nếu có lỗi xử lý
            self.doc_repo.update_status(document, ProcessingStatus.FAILED)
            raise e