import uuid
from typing import Annotated
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.search import SearchPaginatedResponse
from app.services.search_service import SearchService

router = APIRouter(prefix="/search", tags=["Search"])


@router.get(
    "",
    response_model=SearchPaginatedResponse,
    status_code=status.HTTP_200_OK,
    summary="Search documents across keyword, title, tags, subject, folder_id, and semantic vector content",
)
def search_documents(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    keyword: Annotated[
        str | None,
        Query(
            description="Unified search keyword (searches across title, tag name, subject, and semantic PDF content)",
        ),
    ] = None,
    title: Annotated[
        str | None,
        Query(
            description="Filter specifically by document title",
        ),
    ] = None,
    tags: Annotated[
        list[str] | None,
        Query(
            description="Filter specifically by tag names",
        ),
    ] = None,
    subject: Annotated[
        str | None,
        Query(
            description="Filter specifically by subject name",
        ),
    ] = None,
    folder_id: Annotated[
        uuid.UUID | None,
        Query(
            description="Filter specifically by folder UUID",
        ),
    ] = None,
    page: Annotated[
        int,
        Query(
            ge=1,
            description="Page number starting from 1",
        ),
    ] = 1,
    page_size: Annotated[
        int,
        Query(
            ge=1,
            le=100,
            description="Number of items per page (1-100)",
        ),
    ] = 20,
) -> SearchPaginatedResponse:
    service = SearchService(db)
    return service.search(
        user_id=current_user.id,
        keyword=keyword,
        title=title,
        tags=tags,
        subject=subject,
        folder_id=folder_id,
        page=page,
        page_size=page_size,
    )
