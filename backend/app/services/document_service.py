import mimetypes
from pathlib import Path
import time
import uuid

from fastapi import HTTPException, UploadFile, status

from app.core.config import settings
from app.models.document import Document, DocumentChunk, ProcessingStatus
from app.repositories.document_repo import DocumentRepository
from app.repositories.tag_repo import TagRepository
from app.repositories.user_repo import UserRepository
from app.utils.text_extract import (
    extract_blocks,
    extract_text,
)
from app.services.summary_service import generate_summary
from app.services.suggested_question_service import generate_suggested_questions
from app.services.gemini_embedding_provider import (
    GeminiEmbeddingProvider,
    GeminiEmbeddingProviderError,
)
from app.utils.text_chunking import chunk_blocks, count_local_tokens, chunk_text_by_tokens


ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "txt", "pptx", "jpg", "jpeg", "png"}

# Fallback MIME map cho các định dạng mimetypes có thể đoán sai/thiếu trên một số OS
EXTENSION_MIME_OVERRIDES = {
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "pdf": "application/pdf",
}


class DocumentService:

    def __init__(
        self,
        doc_repo: DocumentRepository,
        tag_repo: TagRepository,
        user_repo: UserRepository | None = None,
        embedding_provider: GeminiEmbeddingProvider | None = None,
        sleep=time.sleep,
    ):
        self.doc_repo = doc_repo
        self.tag_repo = tag_repo
        self.user_repo = user_repo
        self.embedding_provider = embedding_provider
        self.sleep = sleep


    def _get_document_or_404(self, document_id: uuid.UUID) -> Document:
        document = self.doc_repo.get_by_id(document_id)
        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Không tìm thấy tài liệu.",
            )
        return document

    def get_metadata(self, document_id: uuid.UUID) -> dict:
        """Tổng hợp dữ liệu cho tính năng View Metadata (mục 2.2)."""
        document = self._get_document_or_404(document_id)

        file_size: int | None
        try:
            file_size = Path(document.file_path).stat().st_size
        except OSError:
            # File có thể đã bị xoá khỏi ổ đĩa dù record DB vẫn còn -> vẫn trả
            # metadata, chỉ để file_size = None thay vì làm sập request.
            file_size = None

        uploader = None
        if self.user_repo is not None:
            uploader = self.user_repo.get_by_id(document.uploaded_by)

        tags = self.tag_repo.get_tags_for_document(document.id)

        return {
            "id": document.id,
            "title": document.title,
            "file_type": document.file_type,
            "file_size": file_size,
            "folder_id": document.folder_id,
            "uploaded_by": {
                "id": document.uploaded_by,
                "full_name": uploader.full_name if uploader else "Không xác định",
            },
            "summary": document.summary,
            "suggested_questions": document.suggested_questions or [],
            "processing_status": document.processing_status,
            "tags": tags,
            "created_at": document.created_at,
        }

    def get_file_for_download(self, document_id: uuid.UUID) -> tuple[Path, str, str]:
        """Trả về (đường dẫn file, tên file hiển thị, media_type) để download.

        Kiểm tra file có thực sự tồn tại trên đĩa trước khi trả về, tránh
        trường hợp record DB còn nhưng file vật lý đã bị xoá/di chuyển.
        """
        document = self._get_document_or_404(document_id)

        file_path = Path(document.file_path)
        if not file_path.is_file():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File không còn tồn tại trên hệ thống.",
            )

        # Đặt lại tên file tải về theo title thay vì tên UUID lưu trên đĩa
        ext = document.file_type.lstrip(".")
        safe_title = document.title.strip() or "document"
        download_name = safe_title if safe_title.lower().endswith(f".{ext}") else f"{safe_title}.{ext}"

        media_type = (
            EXTENSION_MIME_OVERRIDES.get(ext)
            or mimetypes.guess_type(download_name)[0]
            or "application/octet-stream"
        )

        return file_path, download_name, media_type


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
            if document.file_type.lower() == "docx":
                blocks = extract_blocks(document.file_path, "docx")
                text = "\n\n".join(block.text for block in blocks)
                chunks = chunk_blocks(blocks)
            else:
                chunks = chunk_text_by_tokens(
                    text,
                    max_tokens=settings.GEMINI_EMBEDDING_CHUNK_TOKENS,
                    overlap_tokens=settings.GEMINI_EMBEDDING_CHUNK_OVERLAP_TOKENS,
                )
            if not chunks:
                raise ValueError("Khong the trich xuat noi dung tai lieu.")

            provider = self.embedding_provider or GeminiEmbeddingProvider()
            owns_provider = self.embedding_provider is None
            try:
                batches = list(
                    _iter_embedding_batches(
                        chunks,
                        max_tokens=settings.GEMINI_EMBEDDING_BATCH_TOKENS,
                    )
                )
                for batch_index, (batch_start, batch) in enumerate(batches):
                    batch_texts = [
                        chunk.content if hasattr(chunk, "content") else chunk
                        for chunk in batch
                    ]
                    vectors = _embed_batch_with_retries(
                        provider,
                        batch_texts,
                        task_type="RETRIEVAL_DOCUMENT",
                        sleep=self.sleep,
                    )
                    self.doc_repo.add_chunks(
                        [
                            DocumentChunk(
                                document_id=document.id,
                                chunk_index=batch_start + index,
                                content=chunk.content if hasattr(chunk, "content") else chunk,
                                embedding=vector,
                                chunk_metadata=(
                                    {"heading_path": chunk.heading_path}
                                    if hasattr(chunk, "heading_path")
                                    else {}
                                ),
                            )
                            for index, (chunk, vector) in enumerate(zip(batch, vectors))
                        ]
                    )
                    if batch_index < len(batches) - 1:
                        self.sleep(60)
            finally:
                if owns_provider:
                    provider.close()

            suggested_questions = generate_suggested_questions(text, n=3)
            summary = generate_summary(text, title=document.title)
            self.doc_repo.update_status(
                document,
                ProcessingStatus.DONE,
                summary=summary,
                suggested_questions=suggested_questions,
            )

        except Exception as e:
            # Cập nhật trạng thái FAILED nếu có lỗi xử lý
            self.doc_repo.update_status(document, ProcessingStatus.FAILED)
            raise e


def build_embedding_batches(
    chunks: list,
    max_tokens: int = 27000,
) -> list[list[str]]:
    if max_tokens <= 0:
        raise ValueError("max_tokens must be greater than zero")

    batches: list[list[str]] = []
    current: list[str] = []
    current_tokens = 0
    for chunk in chunks:
        chunk_text = chunk.content if hasattr(chunk, "content") else chunk
        chunk_tokens = count_local_tokens(chunk_text)
        if chunk_tokens > max_tokens:
            raise ValueError("Mot chunk vuot qua gioi han token cua batch.")
        if current and current_tokens + chunk_tokens > max_tokens:
            batches.append(current)
            current = []
            current_tokens = 0
        current.append(chunk)
        current_tokens += chunk_tokens
    if current:
        batches.append(current)
    return batches


def _iter_embedding_batches(chunks: list[str], *, max_tokens: int):
    offset = 0
    for batch in build_embedding_batches(chunks, max_tokens=max_tokens):
        yield offset, batch
        offset += len(batch)


def _embed_batch_with_retries(
    provider: GeminiEmbeddingProvider,
    batch: list[str],
    *,
    task_type: str,
    sleep,
) -> list[list[float]]:
    for attempt in range(3):
        try:
            return provider.embed_batch(batch, task_type=task_type)
        except GeminiEmbeddingProviderError as exc:
            if not exc.retryable or attempt == 2:
                raise
            sleep(2 ** (attempt + 1))
    raise AssertionError("unreachable")
