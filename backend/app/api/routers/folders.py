from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_role
from app.schemas.folder import (
    DocumentMove,
    FolderCreate,
    FolderDocumentResponse,
    FolderResponse,
    FolderTreeNode,
    FolderUpdate,
)
from app.services.folder_service import FolderService


router = APIRouter(prefix="/folders", tags=["Organize by Folder"])
teacher_only = require_role("teacher")


@router.post(
    "",
    response_model=FolderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Tao thu muc mon hoc hoac chu de",
)
def create_folder(
    data: FolderCreate,
    current_user=Depends(teacher_only),
    db: Session = Depends(get_db),
):
    return FolderService(db).create(data, current_user.id)


@router.get(
    "",
    response_model=list[FolderResponse],
    summary="Lay danh sach phang cac thu muc cua giao vien",
)
def list_folders(
    current_user=Depends(teacher_only),
    db: Session = Depends(get_db),
):
    return FolderService(db).list_flat(current_user.id)


@router.get(
    "/tree",
    response_model=list[FolderTreeNode],
    summary="Lay cay thu muc Mon hoc - Chu de",
)
def get_folder_tree(
    current_user=Depends(teacher_only),
    db: Session = Depends(get_db),
):
    return FolderService(db).tree(current_user.id)


@router.patch(
    "/documents/{document_id}",
    response_model=FolderDocumentResponse,
    summary="Chuyen tai lieu vao thu muc hoac dua ra ngoai thu muc",
)
def move_document(
    document_id: UUID,
    data: DocumentMove,
    current_user=Depends(teacher_only),
    db: Session = Depends(get_db),
):
    return FolderService(db).move_document(
        document_id, data.folder_id, current_user.id
    )


@router.get(
    "/{folder_id}",
    response_model=FolderResponse,
    summary="Xem chi tiet thu muc",
)
def get_folder(
    folder_id: UUID,
    current_user=Depends(teacher_only),
    db: Session = Depends(get_db),
):
    return FolderService(db).get(folder_id, current_user.id)


@router.patch(
    "/{folder_id}",
    response_model=FolderResponse,
    summary="Doi ten, mon hoc hoac vi tri thu muc",
)
def update_folder(
    folder_id: UUID,
    data: FolderUpdate,
    current_user=Depends(teacher_only),
    db: Session = Depends(get_db),
):
    return FolderService(db).update(folder_id, data, current_user.id)


@router.delete(
    "/{folder_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Xoa de quy cay thu muc, giu lai tai lieu",
)
def delete_folder(
    folder_id: UUID,
    current_user=Depends(teacher_only),
    db: Session = Depends(get_db),
):
    FolderService(db).delete(folder_id, current_user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{folder_id}/documents",
    response_model=list[FolderDocumentResponse],
    summary="Lay tai lieu trong thu muc",
)
def list_folder_documents(
    folder_id: UUID,
    recursive: bool = Query(default=False),
    current_user=Depends(teacher_only),
    db: Session = Depends(get_db),
):
    return FolderService(db).list_documents(
        folder_id, current_user.id, recursive
    )
