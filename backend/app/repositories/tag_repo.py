from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.tag import DocumentTag, Tag


class TagRepository:

    def __init__(self, db: Session):
        self.db = db

    def get_by_name(self, name: str) -> Tag | None:
        """Lấy Tag theo tên.

        Trả về None nếu không tìm thấy.
        """
        stmt = select(Tag).where(Tag.name == name)
        return self.db.scalar(stmt)

    def create(self, name: str) -> Tag:
        """Tạo mới một Tag."""
        tag = Tag(name=name)
        self.db.add(tag)
        self.db.commit()
        self.db.refresh(tag)
        return tag

    def get_or_create(self, name: str) -> Tag:
        """Lấy Tag nếu đã tồn tại, nếu chưa có thì tạo mới."""
        tag = self.get_by_name(name)
        if tag:
            return tag
        return self.create(name)

    def attach_to_document(self, document_id: int, tag_id: int) -> None:
        """Gắn Tag vào Document (nếu chưa được gắn trước đó)."""
        stmt = select(DocumentTag).where(
            DocumentTag.document_id == document_id,
            DocumentTag.tag_id == tag_id,
        )
        exists = self.db.scalar(stmt)

        if not exists:
            self.db.add(DocumentTag(document_id=document_id, tag_id=tag_id))
            self.db.commit()

    def get_tags_for_document(self, document_id: int) -> list[str]:
        """Lấy danh sách tên tất cả các Tag thuộc về một Document."""
        stmt = (
            select(Tag.name)
            .join(DocumentTag, DocumentTag.tag_id == Tag.id)
            .where(DocumentTag.document_id == document_id)
        )
        return list(self.db.scalars(stmt).all())