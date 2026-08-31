from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.document import ProcessingStatus


class DocumentResponse(BaseModel):
    """Response tối giản trả về ngay sau khi upload."""

    id: UUID
    title: str
    file_type: str
    folder_id: UUID | None
    uploaded_by: UUID
    suggested_questions: list[str] = Field(default_factory=list)
    processing_status: ProcessingStatus
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UploaderInfo(BaseModel):
    id: UUID
    full_name: str


class DocumentMetadataResponse(BaseModel):
    """Response đầy đủ cho tính năng View Metadata."""

    id: UUID
    title: str
    file_type: str
    file_size: int | None  # bytes; None nếu không đọc được file trên đĩa
    folder_id: UUID | None
    uploaded_by: UploaderInfo
    summary: str | None
    suggested_questions: list[str] = Field(default_factory=list)
    processing_status: ProcessingStatus
    processing_attempts: int = 0
    processing_started_at: datetime | None = None
    processing_completed_at: datetime | None = None
    processing_last_error: str | None = None
    tags: list[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
