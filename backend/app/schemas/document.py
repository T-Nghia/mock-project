from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.document import ProcessingStatus


class DocumentResponse(BaseModel):
    """Response tối giản trả về ngay sau khi upload."""

    id: UUID
    title: str
    file_type: str
    folder_id: UUID | None
    uploaded_by: UUID
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
    processing_status: ProcessingStatus
    tags: list[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
