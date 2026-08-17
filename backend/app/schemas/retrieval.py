from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: UUID
    document_id: UUID
    chunk_index: int
    content: str
    score: float
    document_title: str | None = None


class Retriever(Protocol):
    def retrieve(
        self,
        *,
        document_id: UUID | None,
        user_id: UUID,
        question: str,
        top_k: int = 5,
    ) -> list[RetrievedChunk]:
        raise NotImplementedError
