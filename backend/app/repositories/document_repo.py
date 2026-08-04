import uuid
from sqlalchemy import func, select
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
        self, document: Document, status, summary: str | None = None
    ) -> Document:
        document.processing_status = status
        if summary is not None:
            document.summary = summary
        self.db.commit()
        self.db.refresh(document)
        return document

    def add_chunks(self, chunks: list[DocumentChunk]) -> None:
        self.db.add_all(chunks)
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