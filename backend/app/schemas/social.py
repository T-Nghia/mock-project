from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class BookmarkStatusResponse(BaseModel):
    document_id: UUID
    bookmarked: bool


class BookmarkedDocumentResponse(BaseModel):
    """1 tài liệu trong danh sách 'Tài liệu đã lưu' của người dùng."""

    id: UUID
    title: str
    file_type: str
    processing_status: str
    bookmarked_at: datetime

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)


class PaginatedBookmarksResponse(BaseModel):
    items: list[BookmarkedDocumentResponse]
    total: int
    page: int
    page_size: int


class CommentCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)

    model_config = ConfigDict(extra="forbid")


class CommentResponse(BaseModel):
    id: UUID
    document_id: UUID
    user_id: UUID
    author_name: str
    content: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PaginatedCommentsResponse(BaseModel):
    items: list[CommentResponse]
    total: int
    page: int
    page_size: int


class RatingUpsert(BaseModel):
    score: int = Field(..., ge=1, le=5)

    model_config = ConfigDict(extra="forbid")


class RatingSummaryResponse(BaseModel):
    document_id: UUID
    average: float | None
    count: int
    my_score: int | None