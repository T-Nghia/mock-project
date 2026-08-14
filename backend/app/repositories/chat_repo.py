import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.chat import ChatMessage, ChatSession


class ChatRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_session(
        self,
        *,
        user_id: uuid.UUID,
        document_id: uuid.UUID,
    ) -> ChatSession:
        session = ChatSession(user_id=user_id, document_id=document_id)
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session

    def get_owned_session(
        self,
        *,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> ChatSession | None:
        stmt = select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == user_id,
        )
        return self.db.scalar(stmt)

    def delete_owned_session(
        self,
        *,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        session = self.get_owned_session(session_id=session_id, user_id=user_id)
        if session is None:
            return
        self.db.delete(session)
        self.db.commit()

    def list_owned_sessions_by_document(
        self,
        *,
        document_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> list[ChatSession]:
        stmt = (
            select(ChatSession)
            .where(
                ChatSession.document_id == document_id,
                ChatSession.user_id == user_id,
            )
            .order_by(ChatSession.created_at.desc(), ChatSession.id.desc())
        )
        return list(self.db.scalars(stmt).all())

    def list_messages(self, *, session_id: uuid.UUID) -> list[ChatMessage]:
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
        )
        return list(self.db.scalars(stmt).all())

    def add_message(
        self,
        *,
        session_id: uuid.UUID,
        role: str,
        content: str,
        source_chunks: list | None = None,
    ) -> ChatMessage:
        message = ChatMessage(
            session_id=session_id,
            role=role,
            content=content,
            source_chunks=source_chunks,
        )
        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)
        return message
