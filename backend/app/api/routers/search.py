import uuid
from typing import Annotated
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.search import SearchPaginatedResponse
from app.services.search_service import SearchService

router = APIRouter(prefix="/search", tags=["Search"])


@router.get(
    "",
    response_model=SearchPaginatedResponse,
    status_code=status.HTTP_200_OK,
    summary="Search documents by Name, Tag, and Subject",
    description=(
        "Search documents flexible filtering across multiple criteria:\n"
        "- **Search by Name (`q`)**: Filter documents matching query substring in title.\n"
        "- **Search by Tag (`tags`)**: Filter documents associated with specified tag names.\n"
        "- **Search by Subject (`subject`)**: Filter documents belonging to folders matching subject name.\n"
        "- **Filter Folder (`folder_id`)**: Filter documents inside a specific folder.\n"
        "\nAll filters can be combined together."
    ),
)
def search_documents(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    q: Annotated[
        str | None,
        Query(
            description="Search query by document name/title",
            example="Giải tích 1",
        ),
    ] = None,
    tags: Annotated[
        list[str] | None,
        Query(
            description="Filter by tag names (pass multiple times e.g. ?tags=de-thi&tags=toan)",
            example=["de-thi"],
        ),
    ] = None,
    subject: Annotated[
        str | None,
        Query(
            description="Filter by subject name",
            example="Toán cao cấp",
        ),
    ] = None,
    folder_id: Annotated[
        uuid.UUID | None,
        Query(
            description="Filter by specific folder UUID",
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
        q=q,
        tags=tags,
        subject=subject,
        folder_id=folder_id,
        page=page,
        page_size=page_size,
    )
