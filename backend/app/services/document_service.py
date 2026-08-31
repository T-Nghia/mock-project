import mimetypes
from pathlib import Path
import time
import uuid
from collections.abc import Sequence
from typing import Literal

from botocore.exceptions import ClientError
from fastapi import HTTPException, UploadFile, status

from app.core.config import settings
from app.models.document import Document, DocumentChunk, ProcessingStatus
from app.models.user import UserRole
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
from app.services.storage import ObjectStorage, get_storage
from app.utils.text_chunking import ChunkData, chunk_blocks, count_local_tokens, chunk_text_by_tokens


ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "txt", "pptx", "jpg", "jpeg", "png"}

# Fallback MIME map cho các định dạng mimetypes có thể đoán sai/thiếu trên một số OS
EXTENSION_MIME_OVERRIDES = {
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "pdf": "application/pdf",
}


def _validate_file_signature(ext: str, header: bytes) -> None:
    signatures = {
        "pdf": (b"%PDF-",),
        "doc": (bytes.fromhex("D0CF11E0A1B11AE1"),),
        "docx": (b"PK\x03\x04",),
        "pptx": (b"PK\x03\x04",),
        "jpg": (b"\xff\xd8\xff",),
        "jpeg": (b"\xff\xd8\xff",),
        "png": (b"\x89PNG\r\n\x1a\n",),
    }
    valid = b"\x00" not in header if ext == "txt" else any(
        header.startswith(signature) for signature in signatures.get(ext, ())
    )
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Noi dung file khong khop voi dinh dang da khai bao.",
        )


class DocumentService:

    def __init__(
        self,
        doc_repo: DocumentRepository,
        tag_repo: TagRepository,
        user_repo: UserRepository | None = None,
        embedding_provider: GeminiEmbeddingProvider | None = None,
        sleep=time.sleep,
        storage: ObjectStorage | None = None,
    ):
        self.doc_repo = doc_repo
        self.tag_repo = tag_repo
        self.user_repo = user_repo
        self.embedding_provider = embedding_provider
        self.sleep = sleep
        self.storage = storage or get_storage()


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
            file_size = self.storage.size(document.file_path)
        except (OSError, ClientError):
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
            "processing_attempts": document.processing_attempts,
            "processing_started_at": document.processing_started_at,
            "processing_completed_at": document.processing_completed_at,
            "processing_last_error": document.processing_last_error,
            "tags": tags,
            "created_at": document.created_at,
        }

    def get_file_for_download(self, document_id: uuid.UUID) -> tuple[bytes, str, str]:
        """Trả về (đường dẫn file, tên file hiển thị, media_type) để download.

        Kiểm tra file có thực sự tồn tại trên đĩa trước khi trả về, tránh
        trường hợp record DB còn nhưng file vật lý đã bị xoá/di chuyển.
        """
        document = self._get_document_or_404(document_id)

        try:
            content = self.storage.read(document.file_path)
        except (OSError, ClientError):
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

        return content, download_name, media_type

    def get_file_for_view(self, document_id: uuid.UUID) -> tuple[bytes, str, str]:
        """Trả về (đường dẫn file, tên file hiển thị, media_type) để xem trực tiếp trên trình duyệt (inline).

        Dùng chung logic phân giải file với get_file_for_download, chỉ khác ở
        cách endpoint gắn Content-Disposition (inline thay vì attachment).
        """
        return self.get_file_for_download(document_id)

    def delete_document(self, document_id: uuid.UUID, current_user) -> None:
        """Xóa tài liệu (record DB + file vật lý trên đĩa).

        Chỉ người đã tải tài liệu lên (chủ sở hữu) hoặc Admin mới được xóa.
        Các dữ liệu liên quan (chunks, tags, chat sessions, bookmark, comment,
        rating) đã được cấu hình ON DELETE CASCADE/SET NULL ở DB nên sẽ tự dọn theo.
        """
        document = self._get_document_or_404(document_id)

        is_owner = document.uploaded_by == current_user.id
        is_admin = current_user.role == UserRole.ADMIN
        if not is_owner and not is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bạn chỉ có thể xóa tài liệu do chính mình tải lên.",
            )

        self.doc_repo.delete(document)
        self.storage.delete(document.file_path)


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

        stream = file.file
        stream.seek(0, 2)
        file_size = stream.tell()
        stream.seek(0)
        if file_size > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="File vượt quá dung lượng cho phép.",
            )

        # 3. Ghi file vào đĩa
        header = stream.read(16)
        stream.seek(0)
        _validate_file_signature(ext, header)
        stored_name = f"{uuid.uuid4().hex}.{ext}"
        content_type = file.content_type or EXTENSION_MIME_OVERRIDES.get(ext) or "application/octet-stream"
        file_location = self.storage.save_stream(stored_name, stream, content_type)

        # 4. Lưu Metadata Document vào DB (Trạng thái PENDING)
        doc_title = title if title else (filename or "Untitled Document")
        document = Document(
            title=doc_title,
            file_path=file_location,
            file_type=ext,
            folder_id=folder_id,
            uploaded_by=uploaded_by,
            processing_status=ProcessingStatus.PENDING,
        )
        try:
            document = self.doc_repo.create(document)
        except Exception:
            self.storage.delete(file_location)
            raise

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

        if document.processing_status == ProcessingStatus.DONE:
            return
        self.doc_repo.update_status(document, ProcessingStatus.PROCESSING)
        if hasattr(self.doc_repo, "delete_chunks"):
            self.doc_repo.delete_chunks(document.id)

        try:
            with self.storage.materialize(
                document.file_path,
                suffix=f".{document.file_type}",
            ) as local_path:
                text = extract_text(str(local_path), document.file_type)
                blocks = (
                    extract_blocks(str(local_path), document.file_type)
                    if document.file_type.lower() in {"docx", "pdf"}
                    else None
                )
            chunks: Sequence[str | ChunkData]
            if blocks is not None:
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
            try:
                self.doc_repo.update_status(document, ProcessingStatus.FAILED, last_error=str(e))
            except TypeError:
                self.doc_repo.update_status(document, ProcessingStatus.FAILED)
            raise


def build_embedding_batches(
    chunks: Sequence[str | ChunkData],
    max_tokens: int = 27000,
) -> list[list[str | ChunkData]]:
    if max_tokens <= 0:
        raise ValueError("max_tokens must be greater than zero")

    batches: list[list[str | ChunkData]] = []
    current: list[str | ChunkData] = []
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


def _iter_embedding_batches(chunks: Sequence[str | ChunkData], *, max_tokens: int):
    offset = 0
    for batch in build_embedding_batches(chunks, max_tokens=max_tokens):
        yield offset, batch
        offset += len(batch)


def _embed_batch_with_retries(
    provider: GeminiEmbeddingProvider,
    batch: list[str],
    *,
    task_type: Literal["RETRIEVAL_DOCUMENT", "RETRIEVAL_QUERY"],
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
