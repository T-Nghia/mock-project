import uuid

from fastapi import HTTPException, status

from app.models.user import User, UserRole
from app.repositories.document_repo import DocumentRepository
from app.repositories.social_repo import SocialRepository
from app.repositories.user_repo import UserRepository


class SocialService:
    def __init__(
        self,
        social_repo: SocialRepository,
        doc_repo: DocumentRepository,
        user_repo: UserRepository,
    ):
        self.social_repo = social_repo
        self.doc_repo = doc_repo
        self.user_repo = user_repo

    def _ensure_document_exists(self, document_id: uuid.UUID) -> None:
        if not self.doc_repo.get_by_id(document_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Không tìm thấy tài liệu.",
            )

    def add_bookmark(self, user: User, document_id: uuid.UUID) -> dict:
        self._ensure_document_exists(document_id)
        self.social_repo.add_bookmark(user.id, document_id)
        return {"document_id": document_id, "bookmarked": True}

    def remove_bookmark(self, user: User, document_id: uuid.UUID) -> dict:
        self._ensure_document_exists(document_id)
        self.social_repo.remove_bookmark(user.id, document_id)
        return {"document_id": document_id, "bookmarked": False}

    def get_bookmark_status(self, user: User, document_id: uuid.UUID) -> dict:
        self._ensure_document_exists(document_id)
        bookmarked = self.social_repo.get_bookmark(user.id, document_id) is not None
        return {"document_id": document_id, "bookmarked": bookmarked}

    def list_my_bookmarks(self, user: User, page: int, page_size: int) -> dict:
        rows, total = self.social_repo.list_bookmarked_documents(user.id, page, page_size)
        items = [
            {
                "id": document.id,
                "title": document.title,
                "file_type": document.file_type,
                "processing_status": document.processing_status,
                "bookmarked_at": bookmark.created_at,
            }
            for document, bookmark in rows
        ]
        return {"items": items, "total": total, "page": page, "page_size": page_size}

    def add_comment(self, user: User, document_id: uuid.UUID, content: str) -> dict:
        self._ensure_document_exists(document_id)
        comment = self.social_repo.add_comment(user.id, document_id, content)
        return self._comment_to_dict(comment, user.full_name)

    def list_comments(self, document_id: uuid.UUID, page: int, page_size: int) -> dict:
        self._ensure_document_exists(document_id)
        comments, total = self.social_repo.list_comments(document_id, page, page_size)

        author_ids = {comment.user_id for comment in comments}
        authors = {
            author_id: (self.user_repo.get_by_id(author_id))
            for author_id in author_ids
        }
        items = [
            self._comment_to_dict(
                comment,
                authors[comment.user_id].full_name if authors.get(comment.user_id) else "Không xác định",
            )
            for comment in comments
        ]
        return {"items": items, "total": total, "page": page, "page_size": page_size}

    def delete_comment(self, user: User, comment_id: uuid.UUID) -> None:
        comment = self.social_repo.get_comment(comment_id)
        if not comment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Không tìm thấy bình luận.",
            )
        is_owner = comment.user_id == user.id
        is_admin = user.role == UserRole.ADMIN
        if not is_owner and not is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bạn chỉ có thể xóa bình luận của chính mình.",
            )
        self.social_repo.delete_comment(comment)

    @staticmethod
    def _comment_to_dict(comment, author_name: str) -> dict:
        return {
            "id": comment.id,
            "document_id": comment.document_id,
            "user_id": comment.user_id,
            "author_name": author_name,
            "content": comment.content,
            "created_at": comment.created_at,
        }

    def set_rating(self, user: User, document_id: uuid.UUID, score: int) -> dict:
        self._ensure_document_exists(document_id)
        self.social_repo.upsert_rating(user.id, document_id, score)
        return self._rating_summary_dict(user, document_id)

    def remove_rating(self, user: User, document_id: uuid.UUID) -> dict:
        self._ensure_document_exists(document_id)
        self.social_repo.delete_rating(user.id, document_id)
        return self._rating_summary_dict(user, document_id)

    def get_rating_summary(self, user: User, document_id: uuid.UUID) -> dict:
        self._ensure_document_exists(document_id)
        return self._rating_summary_dict(user, document_id)

    def _rating_summary_dict(self, user: User, document_id: uuid.UUID) -> dict:
        average, count = self.social_repo.rating_summary(document_id)
        my_rating = self.social_repo.get_rating(user.id, document_id)
        return {
            "document_id": document_id,
            "average": round(average, 2) if average is not None else None,
            "count": count,
            "my_score": my_rating.score if my_rating else None,
        }
    