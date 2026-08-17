from uuid import UUID

from sqlalchemy.orm import Session

from app.repositories.retrieval_repo import RetrievalRepository
from app.schemas.retrieval import RetrievedChunk
from app.utils.text_extract import embed_text


class RetrievalService:
    def __init__(self, db: Session, repository=None):
        self.repository = repository or RetrievalRepository(db)

    def retrieve(
        self,
        *,
        document_id: UUID | None = None,
        user_id: UUID,
        question: str,
        top_k: int = 5,
    ) -> list[RetrievedChunk]:
        """Embed a question and return relevant chunks for single or global document mode."""
        clean_question = question.strip()
        if not clean_question:
            raise ValueError("Cau hoi khong duoc de trong.")
        if not 1 <= top_k <= 20:
            raise ValueError("top_k phai nam trong khoang 1 den 20.")

        return self.repository.retrieve_chunks(
            document_id=document_id,
            user_id=user_id,
            query_embedding=embed_text(clean_question),
            top_k=top_k,
        )
