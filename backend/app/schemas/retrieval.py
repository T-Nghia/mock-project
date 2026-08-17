from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: UUID
    document_id: UUID
    chunk_index: int
    content: str
    score: float
    heading_path: list[str] = field(default_factory=list)


class Retriever(Protocol):
    def retrieve(
        self,
        *,
        document_id: UUID,
        question: str,
        top_k: int = 5,
    ) -> list[RetrievedChunk]:
        raise NotImplementedError
