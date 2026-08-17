import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.social import Bookmark, Comment, Rating


class SocialRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_bookmark(self, user_id: uuid.UUID, document_id: uuid.UUID) -> Bookmark | None:
        return (
            self.db.query(Bookmark)
            .filter(Bookmark.user_id == user_id, Bookmark.document_id == document_id)
            .first()
        )

    def add_bookmark(self, user_id: uuid.UUID, document_id: uuid.UUID) -> Bookmark:
        existing = self.get_bookmark(user_id, document_id)
        if existing:
            return existing
        bookmark = Bookmark(user_id=user_id, document_id=document_id)
        self.db.add(bookmark)
        self.db.commit()
        self.db.refresh(bookmark)
        return bookmark

    def remove_bookmark(self, user_id: uuid.UUID, document_id: uuid.UUID) -> bool:
        bookmark = self.get_bookmark(user_id, document_id)
        if not bookmark:
            return False
        self.db.delete(bookmark)
        self.db.commit()
        return True

    def list_bookmarked_documents(
        self, user_id: uuid.UUID, page: int, page_size: int
    ) -> tuple[list[tuple[Document, "Bookmark"]], int]:
        base_query = (
            self.db.query(Document, Bookmark)
            .join(Bookmark, Bookmark.document_id == Document.id)
            .filter(Bookmark.user_id == user_id)
        )
        total = base_query.count()
        rows = (
            base_query.order_by(Bookmark.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return rows, total

    def add_comment(self, user_id: uuid.UUID, document_id: uuid.UUID, content: str) -> Comment:
        comment = Comment(user_id=user_id, document_id=document_id, content=content.strip())
        self.db.add(comment)
        self.db.commit()
        self.db.refresh(comment)
        return comment

    def get_comment(self, comment_id: uuid.UUID) -> Comment | None:
        return self.db.query(Comment).filter(Comment.id == comment_id).first()

    def list_comments(
        self, document_id: uuid.UUID, page: int, page_size: int
    ) -> tuple[list[Comment], int]:
        base_query = self.db.query(Comment).filter(Comment.document_id == document_id)
        total = base_query.count()
        rows = (
            base_query.order_by(Comment.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return rows, total

    def delete_comment(self, comment: Comment) -> None:
        self.db.delete(comment)
        self.db.commit()

    def get_rating(self, user_id: uuid.UUID, document_id: uuid.UUID) -> Rating | None:
        return (
            self.db.query(Rating)
            .filter(Rating.user_id == user_id, Rating.document_id == document_id)
            .first()
        )

    def upsert_rating(self, user_id: uuid.UUID, document_id: uuid.UUID, score: int) -> Rating:
        rating = self.get_rating(user_id, document_id)
        if rating:
            rating.score = score
        else:
            rating = Rating(user_id=user_id, document_id=document_id, score=score)
            self.db.add(rating)
        self.db.commit()
        self.db.refresh(rating)
        return rating

    def delete_rating(self, user_id: uuid.UUID, document_id: uuid.UUID) -> bool:
        rating = self.get_rating(user_id, document_id)
        if not rating:
            return False
        self.db.delete(rating)
        self.db.commit()
        return True

    def rating_summary(self, document_id: uuid.UUID) -> tuple[float | None, int]:
        average, count = self.db.execute(
            select(func.avg(Rating.score), func.count(Rating.id)).where(
                Rating.document_id == document_id
            )
        ).one()
        return (float(average) if average is not None else None, int(count))
    