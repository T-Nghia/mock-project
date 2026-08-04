import uuid
from sqlalchemy.orm import Session

from app.repositories.search import SearchRepository
from app.schemas.search import SearchPaginatedResponse


class SearchService:
    """Service layer handling document search business logic."""

    def __init__(self, db: Session):
        self.repository = SearchRepository(db)

    def search(
        self,
        q: str | None = None,
        tags: list[str] | None = None,
        subject: str | None = None,
        folder_id: uuid.UUID | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> SearchPaginatedResponse:
        """
        Execute document search across Name, Tag, and Subject filters.
        """
        return self.repository.search_documents(
            q=q,
            tags=tags,
            subject=subject,
            folder_id=folder_id,
            page=page,
            page_size=page_size,
        )
