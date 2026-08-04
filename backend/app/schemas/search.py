import uuid
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class SearchQueryParams(BaseModel):
    """Query parameters for document search with validation."""
    q: str | None = Field(default=None, description="Search query by document name/title (case-insensitive substring or full-text)")
    tags: list[str] | None = Field(default=None, description="Filter by tag names")
    subject: str | None = Field(default=None, description="Filter by subject name")
    folder_id: uuid.UUID | None = Field(default=None, description="Filter by specific folder ID")
    page: int = Field(default=1, ge=1, description="Page number starting from 1")
    page_size: int = Field(default=20, ge=1, le=100, description="Items per page (1-100)")


class DocumentSearchResult(BaseModel):
    """Schema for a single document search result item."""
    id: uuid.UUID
    title: str
    file_type: str
    summary: str | None = None
    folder_id: uuid.UUID | None = None
    folder_name: str | None = None
    subject: str | None = None
    tags: list[str] = Field(default_factory=list)
    uploaded_by: uuid.UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SearchPaginatedResponse(BaseModel):
    """Schema for paginated search results response."""
    items: list[DocumentSearchResult]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total_pages: int = Field(ge=0)

    model_config = ConfigDict(from_attributes=True)
