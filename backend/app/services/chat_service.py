import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.chat import ChatMessage, ChatSession
from app.models.document import ProcessingStatus
from app.models.user import User
from app.repositories.chat_repo import ChatRepository
from app.repositories.document_repo import DocumentRepository
from app.schemas.chat import (
    ChatAnswerResponse,
    ChatCitation,
    ChatMessageResponse,
    ChatSessionDetailResponse,
)
from app.schemas.retrieval import Retriever
from app.services.gemini_provider import GeminiProviderError


REFUSAL_ANSWER = "Không tìm thấy thông tin này trong tài liệu đã chọn."


class ChatService:
    def __init__(self, db: Session, retriever: Retriever, provider):
        self.retriever = retriever
        self.provider = provider
        self.chat_repo = ChatRepository(db)
        self.document_repo = DocumentRepository(db)

    def create_session(
        self,
        *,
        document_id: uuid.UUID | None = None,
        current_user: User,
    ) -> ChatSession:
        if document_id is not None:
            document = self.document_repo.get_by_id(document_id)
            if not document:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Khong tim thay tai lieu.",
                )
            if document.processing_status != ProcessingStatus.DONE:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Tai lieu chua san sang de chat.",
                )
            chunks = self.document_repo.get_chunks(document.id)
            if not any(chunk.embedding is not None for chunk in chunks):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Tai lieu khong co noi dung co the truy xuat.",
                )
            session = self.chat_repo.create_session(
                user_id=current_user.id,
                document_id=document.id,
            )
            session.title = document.title
            return session

        # Global Multi-Document Chat Mode
        session = self.chat_repo.create_session(
            user_id=current_user.id,
            document_id=None,
        )
        session.title = "Chat với Toàn bộ Tài liệu"
        return session

    def get_session(
        self,
        *,
        session_id: uuid.UUID,
        current_user: User,
    ) -> ChatSessionDetailResponse:
        session = self._get_owned_session(session_id, current_user.id)
        messages = [
            self._message_response(message)
            for message in self.chat_repo.list_messages(session_id=session.id)
        ]
        return ChatSessionDetailResponse(
            id=session.id,
            document_id=session.document_id,
            title=session.title,
            created_at=session.created_at,
            messages=messages,
        )

    def ask(
        self,
        *,
        session_id: uuid.UUID,
        content: str,
        current_user: User,
    ) -> ChatAnswerResponse:
        session = self._get_owned_session(session_id, current_user.id)
        history = self.chat_repo.list_messages(session_id=session.id)[-6:]
        self.chat_repo.add_message(
            session_id=session.id,
            role="user",
            content=content,
            source_chunks=None,
        )
        chunks = self.retriever.retrieve(
            document_id=session.document_id,
            user_id=current_user.id,
            question=content,
            top_k=5,
        )
        if not chunks:
            return self._save_answer(session.id, REFUSAL_ANSWER, [])

        try:
            generated = self.provider.answer(
                question=content,
                context=chunks,
                history=history,
            )
        except GeminiProviderError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Dich vu Gemini tam thoi khong kha dung.",
            ) from exc

        if not generated.grounded:
            return self._save_answer(session.id, REFUSAL_ANSWER, [])

        citations = [
            ChatCitation(
                chunk_id=chunk.chunk_id,
                chunk_index=chunk.chunk_index,
                quote=chunk.content[:200],
                score=chunk.score,
                document_title=chunk.document_title,
            )
            for chunk in chunks
        ]
        return self._save_answer(session.id, generated.content, citations)

    def _get_owned_session(
        self,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> ChatSession:
        session = self.chat_repo.get_owned_session(
            session_id=session_id,
            user_id=user_id,
        )
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Khong tim thay phien chat.",
            )
        return session

    def _save_answer(
        self,
        session_id: uuid.UUID,
        content: str,
        citations: list[ChatCitation],
    ) -> ChatAnswerResponse:
        sources_payload = [citation.model_dump(mode="json") for citation in citations]
        self.chat_repo.add_message(
            session_id=session_id,
            role="assistant",
            content=content,
            source_chunks=sources_payload,
        )
        return ChatAnswerResponse(answer=content, sources=citations)

    def _message_response(self, message: ChatMessage) -> ChatMessageResponse:
        raw_sources = message.source_chunks or []
        sources = [ChatCitation.model_validate(raw) for raw in raw_sources]
        return ChatMessageResponse(
            id=message.id,
            role=message.role,
            content=message.content,
            sources=sources,
            created_at=message.created_at,
        )
