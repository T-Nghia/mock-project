import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from collections.abc import Callable

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.document import Document, DocumentChunk, ProcessingStatus
from app.models.folder import Folder
from app.models.tag import DocumentTag, Tag


@dataclass(frozen=True)
class ProcessingSnapshot:
    id: uuid.UUID
    title: str
    file_path: str
    file_type: str
    folder_id: uuid.UUID | None
    uploaded_by: uuid.UUID
    suggested_questions: list[str]
    processing_status: ProcessingStatus
    created_at: datetime


class DocumentRepository:

    def __init__(self, db: Session):
        self.db = db

    def create(self, document: Document) -> Document:
        try:
            self.db.add(document)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        self.db.refresh(document)
        return document

    def get_by_id(self, document_id: uuid.UUID) -> Document | None:
        stmt = select(Document).where(Document.id == document_id)
        return self.db.scalar(stmt)

    def get_for_update(self, document_id: uuid.UUID) -> Document | None:
        stmt = (
            select(Document).where(Document.id == document_id)
            .with_for_update().execution_options(populate_existing=True)
        )
        return self.db.scalar(stmt)

    def stage_delete(self, document: Document) -> None:
        """The deletion service commits this alongside the cleanup job."""
        self.db.delete(document)

    def list_by_folder(self, folder_id: uuid.UUID | None = None) -> list[Document]:
        stmt = select(Document)
        if folder_id is not None:
            stmt = stmt.where(Document.folder_id == folder_id)
        stmt = stmt.order_by(Document.created_at.desc())
        return list(self.db.scalars(stmt).all())

    def list_all(self) -> list[Document]:
        stmt = select(Document).order_by(Document.created_at.desc())
        return list(self.db.scalars(stmt).all())

    def _processing_write(
        self, document_id: uuid.UUID, mutate: Callable[[Document], None],
    ) -> ProcessingSnapshot | None:
        # End a read-only auth/refresh transaction, never discard pending writes.
        if self.db.new or self.db.dirty or self.db.deleted:
            raise RuntimeError("Processing mutation requires a clean session")
        self.db.rollback()
        try:
            document = self.get_for_update(document_id)
            if document is None:
                self.db.rollback()
                return None
            mutate(document)
            snapshot = ProcessingSnapshot(
                id=document.id, title=document.title, file_path=document.file_path,
                file_type=document.file_type, folder_id=document.folder_id,
                uploaded_by=document.uploaded_by,
                suggested_questions=list(document.suggested_questions or []),
                processing_status=document.processing_status, created_at=document.created_at,
            )
            self.db.commit()
            return snapshot
        except Exception:
            self.db.rollback()
            raise

    def is_present(self, document_id: uuid.UUID) -> bool:
        if self.db.new or self.db.dirty or self.db.deleted:
            raise RuntimeError("Processing read requires a clean session")
        try:
            return self.db.scalar(select(Document.id).where(Document.id == document_id)) is not None
        finally:
            self.db.rollback()

    def start_processing(self, document_id: uuid.UUID) -> ProcessingSnapshot | None:
        def start(document):
            if document.processing_status != ProcessingStatus.DONE:
                self._set_status(document, ProcessingStatus.PROCESSING)
                self.db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document_id))
        return self._processing_write(document_id, start)

    def prepare_retry(
        self, document_id: uuid.UUID, authorize: Callable[[Document], None],
    ) -> ProcessingSnapshot | None:
        def reset(document):
            authorize(document)
            self._set_status(document, ProcessingStatus.PENDING)
        return self._processing_write(document_id, reset)

    def update_status(
        self,
        document_id: uuid.UUID,
        status: ProcessingStatus,
        summary: str | None = None,
        suggested_questions: list[str] | None = None,
        last_error: str | None = None,
    ) -> bool:
        return self._processing_write(document_id, lambda document: self._set_status(
            document, status, summary, suggested_questions, last_error,
        )) is not None

    @staticmethod
    def _set_status(
        document: Document, status: ProcessingStatus, summary: str | None = None,
        suggested_questions: list[str] | None = None, last_error: str | None = None,
    ) -> None:
        document.processing_status = status
        if summary is not None:
            document.summary = summary
        if suggested_questions is not None:
            document.suggested_questions = suggested_questions
        if status.value == "pending":
            document.processing_started_at = None
            document.processing_completed_at = None
            document.processing_last_error = None
        elif status.value == "processing":
            document.processing_attempts += 1
            document.processing_started_at = datetime.now(timezone.utc)
            document.processing_completed_at = None
            document.processing_last_error = None
        elif status.value == "retrying":
            document.processing_completed_at = None
            document.processing_last_error = last_error
        elif status.value == "done":
            document.processing_completed_at = datetime.now(timezone.utc)
            document.processing_last_error = None
        elif status.value == "failed":
            document.processing_completed_at = datetime.now(timezone.utc)
            document.processing_last_error = last_error

    def add_chunks(self, document_id: uuid.UUID, chunks: list[DocumentChunk]) -> bool:
        if any(chunk.document_id != document_id for chunk in chunks):
            raise ValueError("Chunk belongs to another document")
        return self._processing_write(document_id, lambda _: self.db.add_all(chunks)) is not None

    def delete_chunks(self, document_id: uuid.UUID) -> bool:
        def remove(_):
            self.db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document_id))
        return self._processing_write(document_id, remove) is not None

    def set_task_id(self, document_id: uuid.UUID, task_id: str | None) -> bool:
        return self._processing_write(
            document_id, lambda document: setattr(document, "processing_task_id", task_id),
        ) is not None

    def get_chunks(self, document_id: uuid.UUID) -> list[DocumentChunk]:
        stmt = (
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index)
        )
        return list(self.db.scalars(stmt).all())

    def search(
        self,
        name: str | None = None,
        tag: str | None = None,
        subject: str | None = None,
    ) -> list[Document]:
        stmt = select(Document).distinct()

        if name:
            stmt = stmt.where(Document.title.ilike(f"%{name}%"))

        if subject:
            # Dùng outerjoin để phòng trường hợp document không thuộc folder nào vẫn không bị lỗi
            stmt = stmt.outerjoin(Folder, Document.folder_id == Folder.id).where(
                Folder.subject.ilike(f"%{subject}%")
            )

        if tag:
            stmt = (
                stmt.join(DocumentTag, DocumentTag.document_id == Document.id)
                .join(Tag, Tag.id == DocumentTag.tag_id)
                .where(Tag.name.ilike(f"%{tag}%"))
            )

        stmt = stmt.order_by(Document.created_at.desc())
        return list(self.db.scalars(stmt).all())

    def count_all(self) -> int:
        stmt = select(func.count(Document.id))
        return self.db.scalar(stmt) or 0

    def uploads_over_time(self, days: int = 14):
        date_col = func.date(Document.created_at)
        stmt = (
            select(date_col, func.count(Document.id))
            .group_by(date_col)
            .order_by(date_col.desc())
            .limit(days)
        )
        rows = self.db.execute(stmt).all()
        return list(reversed(rows))
