from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChatSessionCreate(BaseModel):
    document_id: UUID

    model_config = ConfigDict(extra="forbid")


class ChatQuestionRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)

    model_config = ConfigDict(extra="forbid")

    @field_validator("content", mode="before")
    @classmethod
    def normalize_content(cls, value):
        if not isinstance(value, str):
            return value
        clean = value.strip()
        if not clean:
            raise ValueError("Cau hoi khong duoc de trong.")
        return clean


class ChatCitation(BaseModel):
    chunk_id: UUID
    chunk_index: int
    quote: str
    score: float


class ChatMessageResponse(BaseModel):
    id: UUID
    role: Literal["user", "assistant"]
    content: str
    sources: list[ChatCitation]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChatSessionResponse(BaseModel):
    id: UUID
    document_id: UUID
    title: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChatSessionDetailResponse(ChatSessionResponse):
    messages: list[ChatMessageResponse]


class ChatAnswerResponse(BaseModel):
    answer: str
    sources: list[ChatCitation]
