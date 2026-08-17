import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permissions import Permission
from app.core.security import get_current_user, require_permission
from app.models.user import User
from app.repositories.document_repo import DocumentRepository
from app.repositories.social_repo import SocialRepository
from app.repositories.user_repo import UserRepository
from app.schemas.social import (
    BookmarkStatusResponse,
    CommentCreate,
    CommentResponse,
    PaginatedBookmarksResponse,
    PaginatedCommentsResponse,
    RatingSummaryResponse,
    RatingUpsert,
)
from app.services.social_service import SocialService

router = APIRouter(prefix="", tags=["User Features"])

PageParam = Annotated[int, Query(ge=1, description="Page number starting from 1")]
PageSizeParam = Annotated[int, Query(ge=1, le=100, description="Items per page (1-100)")]


def _build_service(db: Session) -> SocialService:
    return SocialService(
        social_repo=SocialRepository(db),
        doc_repo=DocumentRepository(db),
        user_repo=UserRepository(db),
    )

@router.post(
    "/documents/{document_id}/bookmark",
    response_model=BookmarkStatusResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_bookmark(
    document_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_permission(Permission.SOCIAL_INTERACT))],
    db: Annotated[Session, Depends(get_db)],
):
    """Lưu tài liệu vào danh sách bookmark của tôi (idempotent)."""
    return _build_service(db).add_bookmark(current_user, document_id)


@router.delete(
    "/documents/{document_id}/bookmark",
    response_model=BookmarkStatusResponse,
)
def remove_bookmark(
    document_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_permission(Permission.SOCIAL_INTERACT))],
    db: Annotated[Session, Depends(get_db)],
):
    """Bỏ lưu tài liệu (idempotent — gọi lại nhiều lần không lỗi)."""
    return _build_service(db).remove_bookmark(current_user, document_id)


@router.get(
    "/documents/{document_id}/bookmark",
    response_model=BookmarkStatusResponse,
)
def get_bookmark_status(
    document_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """Kiểm tra tài liệu này đã được tôi bookmark chưa."""
    return _build_service(db).get_bookmark_status(current_user, document_id)


@router.get(
    "/me/bookmarks",
    response_model=PaginatedBookmarksResponse,
)
def list_my_bookmarks(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    page: PageParam = 1,
    page_size: PageSizeParam = 20,
):
    """Danh sách tài liệu tôi đã bookmark."""
    return _build_service(db).list_my_bookmarks(current_user, page, page_size)


@router.post(
    "/documents/{document_id}/comments",
    response_model=CommentResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_comment(
    document_id: uuid.UUID,
    payload: CommentCreate,
    current_user: Annotated[User, Depends(require_permission(Permission.SOCIAL_INTERACT))],
    db: Annotated[Session, Depends(get_db)],
):
    """Bình luận vào tài liệu."""
    return _build_service(db).add_comment(current_user, document_id, payload.content)


@router.get(
    "/documents/{document_id}/comments",
    response_model=PaginatedCommentsResponse,
)
def list_comments(
    document_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    page: PageParam = 1,
    page_size: PageSizeParam = 20,
):
    """Danh sách bình luận của 1 tài liệu, mới nhất trước."""
    return _build_service(db).list_comments(document_id, page, page_size)


@router.delete(
    "/comments/{comment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_comment(
    comment_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_permission(Permission.SOCIAL_INTERACT))],
    db: Annotated[Session, Depends(get_db)],
):
    """Xóa bình luận — chỉ chủ bình luận hoặc Admin."""
    _build_service(db).delete_comment(current_user, comment_id)


@router.put(
    "/documents/{document_id}/rating",
    response_model=RatingSummaryResponse,
)
def set_rating(
    document_id: uuid.UUID,
    payload: RatingUpsert,
    current_user: Annotated[User, Depends(require_permission(Permission.SOCIAL_INTERACT))],
    db: Annotated[Session, Depends(get_db)],
):
    """Đánh giá tài liệu (1-5 sao). Gọi lại sẽ ghi đè đánh giá cũ của chính mình."""
    return _build_service(db).set_rating(current_user, document_id, payload.score)


@router.delete(
    "/documents/{document_id}/rating",
    response_model=RatingSummaryResponse,
)
def remove_rating(
    document_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_permission(Permission.SOCIAL_INTERACT))],
    db: Annotated[Session, Depends(get_db)],
):
    """Gỡ đánh giá của tôi khỏi tài liệu (idempotent)."""
    return _build_service(db).remove_rating(current_user, document_id)


@router.get(
    "/documents/{document_id}/rating",
    response_model=RatingSummaryResponse,
)
def get_rating_summary(
    document_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """Điểm trung bình + số lượt đánh giá + điểm của riêng tôi (nếu có)."""
    return _build_service(db).get_rating_summary(current_user, document_id)
