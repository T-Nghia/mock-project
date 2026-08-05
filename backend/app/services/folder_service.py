import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.folder import Folder
from app.repositories.folder_repo import FolderRepository
from app.schemas.folder import FolderCreate, FolderTreeNode, FolderUpdate


class FolderService:
    def __init__(self, db: Session):
        self.repo = FolderRepository(db)

    def _owned_folder_or_404(
        self, folder_id: uuid.UUID, owner_id: uuid.UUID
    ) -> Folder:
        folder = self.repo.get_owned(folder_id, owner_id)
        if folder is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Thu muc khong ton tai hoac khong thuoc quyen quan ly cua ban",
            )
        return folder

    def _ensure_unique_sibling_name(
        self,
        *,
        owner_id: uuid.UUID,
        parent_folder_id: uuid.UUID | None,
        name: str,
        exclude_id: uuid.UUID | None = None,
    ) -> None:
        if self.repo.sibling_name_exists(
            owner_id=owner_id,
            parent_folder_id=parent_folder_id,
            name=name,
            exclude_id=exclude_id,
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Da ton tai thu muc cung ten trong cung thu muc cha",
            )

    @staticmethod
    def _same_text(left: str | None, right: str | None) -> bool:
        return (left or "").strip().casefold() == (right or "").strip().casefold()

    def create(self, data: FolderCreate, owner_id: uuid.UUID) -> Folder:
        parent = None
        if data.parent_folder_id is not None:
            parent = self._owned_folder_or_404(data.parent_folder_id, owner_id)

        if parent is not None:
            if data.subject is not None and not self._same_text(data.subject, parent.subject):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Mon hoc cua thu muc con phai trung voi thu muc cha",
                )
            subject = parent.subject or data.subject or parent.name
        else:
            subject = data.subject or data.name

        self._ensure_unique_sibling_name(
            owner_id=owner_id,
            parent_folder_id=data.parent_folder_id,
            name=data.name,
        )
        return self.repo.create(
            name=data.name,
            parent_folder_id=data.parent_folder_id,
            subject=subject,
            owner_id=owner_id,
        )

    def list_flat(self, owner_id: uuid.UUID) -> list[Folder]:
        return self.repo.list_owned(owner_id)

    def tree(self, owner_id: uuid.UUID) -> list[FolderTreeNode]:
        folders = self.repo.list_owned(owner_id)
        nodes = {
            folder.id: FolderTreeNode.model_validate(folder)
            for folder in folders
        }
        roots: list[FolderTreeNode] = []
        for folder in folders:
            node = nodes[folder.id]
            parent = nodes.get(folder.parent_folder_id)
            if parent is None:
                roots.append(node)
            else:
                parent.children.append(node)
        return roots

    def get(self, folder_id: uuid.UUID, owner_id: uuid.UUID) -> Folder:
        return self._owned_folder_or_404(folder_id, owner_id)

    def update(
        self, folder_id: uuid.UUID, data: FolderUpdate, owner_id: uuid.UUID
    ) -> Folder:
        folder = self._owned_folder_or_404(folder_id, owner_id)
        fields = data.model_fields_set

        if "name" in fields and data.name is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Ten thu muc khong duoc de trong",
            )
        name = data.name if "name" in fields else folder.name

        if "parent_folder_id" in fields:
            parent_id = data.parent_folder_id
        else:
            parent_id = folder.parent_folder_id

        parent = None
        if parent_id is not None:
            parent = self._owned_folder_or_404(parent_id, owner_id)
            subtree_ids = self.repo.subtree_ids(folder.id, owner_id)
            if parent.id in subtree_ids:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Khong the chuyen thu muc vao chinh no hoac thu muc con cua no",
                )

        if parent is not None:
            if (
                "subject" in fields
                and data.subject is not None
                and not self._same_text(data.subject, parent.subject)
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Mon hoc cua thu muc con phai trung voi thu muc cha",
                )
            subject = parent.subject or data.subject or parent.name
        elif "subject" in fields:
            subject = data.subject or name
        else:
            subject = folder.subject or name

        self._ensure_unique_sibling_name(
            owner_id=owner_id,
            parent_folder_id=parent_id,
            name=name,
            exclude_id=folder.id,
        )

        parent_changed = parent_id != folder.parent_folder_id
        subject_changed = not self._same_text(subject, folder.subject)
        return self.repo.update(
            folder,
            name=name,
            parent_folder_id=parent_id,
            subject=subject,
            propagate_subject=parent_changed or subject_changed,
        )

    def delete(self, folder_id: uuid.UUID, owner_id: uuid.UUID) -> None:
        folder = self._owned_folder_or_404(folder_id, owner_id)
        self.repo.delete_subtree(folder)

    def move_document(
        self,
        document_id: uuid.UUID,
        folder_id: uuid.UUID | None,
        owner_id: uuid.UUID,
    ):
        document = self.repo.get_owned_document(document_id, owner_id)
        if document is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tai lieu khong ton tai hoac khong thuoc quyen quan ly cua ban",
            )

        if folder_id is not None:
            self._owned_folder_or_404(folder_id, owner_id)
        return self.repo.move_document(document, folder_id)

    def list_documents(
        self,
        folder_id: uuid.UUID,
        owner_id: uuid.UUID,
        recursive: bool,
    ):
        folder = self._owned_folder_or_404(folder_id, owner_id)
        folder_ids = (
            self.repo.subtree_ids(folder.id, owner_id) if recursive else [folder.id]
        )
        return self.repo.list_documents(owner_id=owner_id, folder_ids=folder_ids)
