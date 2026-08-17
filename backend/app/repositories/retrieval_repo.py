from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.document import Document, DocumentChunk, ProcessingStatus
from app.models.social import Bookmark
from app.schemas.retrieval import RetrievedChunk


class RetrievalRepository:
    def __init__(self, db: Session):
        self.db = db

    def retrieve_chunks(
        self,
        *,
        document_id: UUID | None,
        user_id: UUID,
        query_embedding: list[float],
        top_k: int,
    ) -> list[RetrievedChunk]:
        """
        Return chunks ordered by vector relevance.
        If document_id is provided: filter by single document.
        If document_id is None: filter across all documents owned (uploaded_by) or bookmarked by user.
        """
        distance = DocumentChunk.embedding.cosine_distance(query_embedding).label("distance")

        stmt = (
            select(DocumentChunk, Document.title, distance)
            .join(Document, Document.id == DocumentChunk.document_id)
        )

        if document_id is not None:
            stmt = stmt.where(DocumentChunk.document_id == document_id)
        else:
            bookmarked_subquery = (
                select(Bookmark.document_id).where(Bookmark.user_id == user_id)
            )
            stmt = stmt.where(
                or_(
                    Document.uploaded_by == user_id,
                    Document.id.in_(bookmarked_subquery),
                )
            )

        stmt = (
            stmt.where(
                DocumentChunk.embedding.is_not(None),
                Document.processing_status == ProcessingStatus.DONE,
            )
            .order_by(distance.asc(), DocumentChunk.chunk_index.asc())
            .limit(top_k)
        )
        rows = self.db.execute(stmt).all()

        return [
            RetrievedChunk(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                score=max(-1.0, min(1.0, 1.0 - float(distance_value))),
                document_title=doc_title,
            )
            for chunk, doc_title, distance_value in rows
        ]
