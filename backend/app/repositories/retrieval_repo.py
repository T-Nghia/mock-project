from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document, DocumentChunk, ProcessingStatus
from app.schemas.retrieval import RetrievedChunk


class RetrievalRepository:
    def __init__(self, db: Session):
        self.db = db

    def retrieve_chunks(
        self,
        *,
        document_id: UUID,
        query_embedding: list[float],
        top_k: int,
    ) -> list[RetrievedChunk]:
        """Return chunks from one document ordered by vector relevance."""
        distance = DocumentChunk.embedding.cosine_distance(query_embedding).label("distance")
        stmt = (
            select(DocumentChunk, distance)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(
                DocumentChunk.document_id == document_id,
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
                heading_path=(chunk.chunk_metadata or {}).get("heading_path", []),
            )
            for chunk, distance_value in rows
        ]
