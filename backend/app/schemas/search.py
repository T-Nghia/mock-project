import uuid
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class SearchQueryParams(BaseModel):
    title: str | None = Field(default=None)
    tags: list[str] | None = Field(default=None)
    subject: str | None = Field(default=None)
    folder_id: uuid.UUID | None = Field(default=None)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class DocumentSearchResult(BaseModel):
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
    items: list[DocumentSearchResult]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total_pages: int = Field(ge=0)

    model_config = ConfigDict(from_attributes=True)
