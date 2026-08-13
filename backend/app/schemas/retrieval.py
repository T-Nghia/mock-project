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


class Retriever(Protocol):
    def retrieve(
        self,
        *,
        document_id: UUID,
        question: str,
        top_k: int = 5,
    ) -> list[RetrievedChunk]:
        raise NotImplementedError
