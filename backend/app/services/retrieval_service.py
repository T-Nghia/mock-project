from uuid import UUID

from sqlalchemy.orm import Session

from app.repositories.retrieval_repo import RetrievalRepository
from app.schemas.retrieval import RetrievedChunk
from app.services.gemini_embedding_provider import GeminiEmbeddingProvider


class RetrievalService:
    def __init__(self, db: Session, repository=None, embedding_provider=None):
        self.repository = repository or RetrievalRepository(db)
        self.embedding_provider = embedding_provider

    def retrieve(
        self,
        *,
        document_id: UUID,
        question: str,
        top_k: int = 5,
    ) -> list[RetrievedChunk]:
        """Embed a question and return relevant chunks from one document."""
        clean_question = question.strip()
        if not clean_question:
            raise ValueError("Cau hoi khong duoc de trong.")
        if not 1 <= top_k <= 20:
            raise ValueError("top_k phai nam trong khoang 1 den 20.")

        provider = self.embedding_provider or GeminiEmbeddingProvider()
        owns_provider = self.embedding_provider is None
        try:
            query_embedding = provider.embed_batch(
                [clean_question],
                task_type="RETRIEVAL_QUERY",
            )[0]
            return self.repository.retrieve_chunks(
                document_id=document_id,
                query_embedding=query_embedding,
                top_k=top_k,
            )
        finally:
            if owns_provider:
                provider.close()
