from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _clean_required_text(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("Khong duoc de trong")
    return cleaned


def _clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


class FolderCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    parent_folder_id: UUID | None = None
    subject: str | None = Field(default=None, max_length=255)

    _clean_name = field_validator("name")(_clean_required_text)
    _clean_subject = field_validator("subject")(_clean_optional_text)

    model_config = ConfigDict(extra="forbid")


class FolderUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    parent_folder_id: UUID | None = None
    subject: str | None = Field(default=None, max_length=255)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        return None if value is None else _clean_required_text(value)

    _clean_subject = field_validator("subject")(_clean_optional_text)

    model_config = ConfigDict(extra="forbid")


class FolderResponse(BaseModel):
    id: UUID
    name: str
    parent_folder_id: UUID | None
    subject: str | None
    owner_id: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FolderTreeNode(FolderResponse):
    children: list["FolderTreeNode"] = Field(default_factory=list)


class DocumentMove(BaseModel):
    folder_id: UUID | None = None

    model_config = ConfigDict(extra="forbid")


class FolderDocumentResponse(BaseModel):
    id: UUID
    title: str
    file_path: str
    file_type: str
    folder_id: UUID | None
    uploaded_by: UUID
    summary: str | None
    processing_status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)
