import uuid
from sqlalchemy.orm import Session

from app.repositories.search_repo import SearchRepository
from app.schemas.search import SearchPaginatedResponse


class SearchService:

    def __init__(self, db: Session):
        self.repository = SearchRepository(db)

    def search(
        self,
        keyword: str | None = None,
        title: str | None = None,
        tags: list[str] | None = None,
        subject: str | None = None,
        folder_id: uuid.UUID | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> SearchPaginatedResponse:

        return self.repository.search_documents(
            keyword=keyword,
            title=title,
            tags=tags,
            subject=subject,
            folder_id=folder_id,
            page=page,
            page_size=page_size,
        )
