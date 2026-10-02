from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.folder import Folder

if TYPE_CHECKING:
    from app.models.document import Document


class FolderRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, folder_id: uuid.UUID) -> Folder | None:
        return self.db.query(Folder).filter(Folder.id == folder_id).first()

    def get_owned(self, folder_id: uuid.UUID, owner_id: uuid.UUID) -> Folder | None:
        return (
            self.db.query(Folder)
            .filter(Folder.id == folder_id, Folder.owner_id == owner_id)
            .first()
        )

    def list_owned(self, owner_id: uuid.UUID) -> list[Folder]:
        return (
            self.db.query(Folder)
            .filter(Folder.owner_id == owner_id)
            .order_by(Folder.created_at.asc(), Folder.name.asc())
            .all()
        )

    def sibling_name_exists(
        self,
        *,
        owner_id: uuid.UUID,
        parent_folder_id: uuid.UUID | None,
        name: str,
        exclude_id: uuid.UUID | None = None,
    ) -> bool:
        query = self.db.query(Folder.id).filter(
            Folder.owner_id == owner_id,
            func.lower(Folder.name) == name.lower(),
        )
        if parent_folder_id is None:
            query = query.filter(Folder.parent_folder_id.is_(None))
        else:
            query = query.filter(Folder.parent_folder_id == parent_folder_id)
        if exclude_id is not None:
            query = query.filter(Folder.id != exclude_id)
        return query.first() is not None

    def create(
        self,
        *,
        name: str,
        parent_folder_id: uuid.UUID | None,
        subject: str | None,
        owner_id: uuid.UUID,
    ) -> Folder:
        folder = Folder(
            name=name,
            parent_folder_id=parent_folder_id,
            subject=subject,
            owner_id=owner_id,
        )
        self.db.add(folder)
        self.db.commit()
        self.db.refresh(folder)
        return folder

    def subtree_ids(self, folder_id: uuid.UUID, owner_id: uuid.UUID) -> list[uuid.UUID]:
        folders = self.list_owned(owner_id)
        children: dict[uuid.UUID, list[uuid.UUID]] = {}
        for item in folders:
            if item.parent_folder_id is not None:
                children.setdefault(item.parent_folder_id, []).append(item.id)

        result: list[uuid.UUID] = []
        stack = [folder_id]
        visited: set[uuid.UUID] = set()
        while stack:
            current_id = stack.pop()
            if current_id in visited:
                continue
            visited.add(current_id)
            result.append(current_id)
            stack.extend(children.get(current_id, []))
        return result

    def update(
        self,
        folder: Folder,
        *,
        name: str,
        parent_folder_id: uuid.UUID | None,
        subject: str | None,
        propagate_subject: bool,
    ) -> Folder:
        folder.name = name
        folder.parent_folder_id = parent_folder_id
        folder.subject = subject

        if propagate_subject:
            descendant_ids = self.subtree_ids(folder.id, folder.owner_id)[1:]
            if descendant_ids:
                (
                    self.db.query(Folder)
                    .filter(Folder.id.in_(descendant_ids))
                    .update({Folder.subject: subject}, synchronize_session=False)
                )

        self.db.commit()
        self.db.refresh(folder)
        return folder

    def delete_subtree(self, folder: Folder) -> None:
        from app.models.document import Document

        folder_ids = self.subtree_ids(folder.id, folder.owner_id)
        if folder_ids:
            (
                self.db.query(Document)
                .filter(Document.folder_id.in_(folder_ids))
                .update({Document.folder_id: None}, synchronize_session=False)
            )
            for folder_id in reversed(folder_ids):
                self.db.query(Folder).filter(Folder.id == folder_id).delete(
                    synchronize_session=False
                )
        self.db.commit()

    def get_owned_document(
        self, document_id: uuid.UUID, owner_id: uuid.UUID
    ) -> Document | None:
        from app.models.document import Document

        return (
            self.db.query(Document)
            .filter(Document.id == document_id, Document.uploaded_by == owner_id)
            .first()
        )

    def move_document(self, document: Document, folder_id: uuid.UUID | None) -> Document:
        document.folder_id = folder_id
        self.db.commit()
        self.db.refresh(document)
        return document

    def list_documents(
        self, *, owner_id: uuid.UUID, folder_ids: list[uuid.UUID]
    ) -> list[Document]:
        from app.models.document import Document

        return (
            self.db.query(Document)
            .filter(
                Document.uploaded_by == owner_id,
                Document.folder_id.in_(folder_ids),
            )
            .order_by(Document.created_at.desc(), Document.title.asc())
            .all()
        )
