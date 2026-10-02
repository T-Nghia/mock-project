import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.folder import Folder
from app.models.user import User


class DashboardRepository:
    def __init__(self, db: Session):
        self.db = db

    def count_documents(self, owner_id: uuid.UUID | None = None) -> int:
        stmt = select(func.count(Document.id))
        if owner_id is not None:
            stmt = stmt.where(Document.uploaded_by == owner_id)
        return self.db.scalar(stmt) or 0

    def count_users(self) -> int:
        return self.db.scalar(select(func.count(User.id))) or 0

    def uploads_by_day(
        self,
        owner_id: uuid.UUID | None,
        start_date: date,
        end_date: date,
    ) -> dict[date, int]:
        upload_date = func.date(Document.created_at)
        stmt = (
            select(upload_date, func.count(Document.id))
            .where(upload_date >= start_date.isoformat(), upload_date <= end_date.isoformat())
            .group_by(upload_date)
        )
        if owner_id is not None:
            stmt = stmt.where(Document.uploaded_by == owner_id)
        return {
            date.fromisoformat(str(uploaded_on)): int(count)
            for uploaded_on, count in self.db.execute(stmt).all()
        }

    def documents_by_folder(
        self, owner_id: uuid.UUID | None = None
    ) -> list[tuple[str, int]]:
        label = func.coalesce(Folder.name, "Uncategorized")
        stmt = (
            select(label, func.count(Document.id))
            .select_from(Document)
            .outerjoin(Folder, Document.folder_id == Folder.id)
            .group_by(label)
            .order_by(label.asc())
        )
        if owner_id is not None:
            stmt = stmt.where(Document.uploaded_by == owner_id)
        return [(str(name), int(count)) for name, count in self.db.execute(stmt).all()]

    def users_by_role(self) -> list[tuple[str, int]]:
        stmt = (
            select(User.role, func.count(User.id))
            .group_by(User.role)
            .order_by(User.role.asc())
        )
        return [
            (str(getattr(role, "value", role)).lower(), int(count))
            for role, count in self.db.execute(stmt).all()
        ]
