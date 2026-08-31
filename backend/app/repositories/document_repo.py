import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.document import Document, DocumentChunk
from app.models.folder import Folder
from app.models.tag import DocumentTag, Tag


class DocumentRepository:

    def __init__(self, db: Session):
        self.db = db

    def create(self, document: Document) -> Document:
        self.db.add(document)
        self.db.commit()
        self.db.refresh(document)
        return document

    def get_by_id(self, document_id: uuid.UUID) -> Document | None:
        stmt = select(Document).where(Document.id == document_id)
        return self.db.scalar(stmt)

    def delete(self, document: Document) -> None:
        self.db.delete(document)
        self.db.commit()

    def list_by_folder(self, folder_id: uuid.UUID | None = None) -> list[Document]:
        stmt = select(Document)
        if folder_id is not None:
            stmt = stmt.where(Document.folder_id == folder_id)
        stmt = stmt.order_by(Document.created_at.desc())
        return list(self.db.scalars(stmt).all())

    def list_all(self) -> list[Document]:
        stmt = select(Document).order_by(Document.created_at.desc())
        return list(self.db.scalars(stmt).all())

    def update_status(
        self,
        document: Document,
        status,
        summary: str | None = None,
        suggested_questions: list[str] | None = None,
        last_error: str | None = None,
    ) -> Document:
        document.processing_status = status
        if summary is not None:
            document.summary = summary
        if suggested_questions is not None:
            document.suggested_questions = suggested_questions
        if status.value == "processing":
            document.processing_attempts += 1
            document.processing_started_at = datetime.now(timezone.utc)
            document.processing_completed_at = None
            document.processing_last_error = None
        elif status.value == "done":
            document.processing_completed_at = datetime.now(timezone.utc)
            document.processing_last_error = None
        elif status.value == "failed":
            document.processing_completed_at = datetime.now(timezone.utc)
            document.processing_last_error = last_error
        self.db.commit()
        self.db.refresh(document)
        return document

    def add_chunks(self, chunks: list[DocumentChunk]) -> None:
        self.db.add_all(chunks)
        self.db.commit()

    def delete_chunks(self, document_id: uuid.UUID) -> None:
        self.db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document_id))
        self.db.commit()

    def set_task_id(self, document: Document, task_id: str | None) -> None:
        document.processing_task_id = task_id
        self.db.commit()

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
