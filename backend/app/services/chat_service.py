import uuid
import re
from typing import NoReturn

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
    ChatSessionListResponse,
    ChatSessionResponse,
)
from app.schemas.retrieval import Retriever
from app.services.gemini_provider import GeminiProviderError


REFUSAL_ANSWER = "Không tìm thấy thông tin này trong tài liệu đã chọn."
MAX_CITATION_QUOTE_CHARS = 400


def build_source_quote(content: str, max_chars: int = MAX_CITATION_QUOTE_CHARS) -> str:
    text = re.sub(r"\s+", " ", content).strip()
    if len(text) <= max_chars:
        return text

    candidate = text[: max_chars + 1]
    sentence_end = max(candidate.rfind("."), candidate.rfind("!"), candidate.rfind("?"))
    if sentence_end >= max_chars // 2:
        return candidate[: sentence_end + 1].strip()

    word_end = candidate.rfind(" ", 0, max_chars)
    if word_end > 0:
        return candidate[:word_end].rstrip() + "…"
    return candidate[:max_chars].rstrip() + "…"


class ChatService:
    def __init__(self, db: Session, retriever: Retriever, provider):
        self.db = db
        self.retriever = retriever
        self.provider = provider
        self.chat_repo = ChatRepository(db)
        self.document_repo = DocumentRepository(db)

    def create_session(
        self,
        *,
        document_id: uuid.UUID,
        current_user: User,
    ) -> ChatSession:
        try:
            # Serialize the FK insert with document deletion. No external I/O
            # occurs while this document lock is held.
            document = self.document_repo.get_for_update(document_id)
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
            return self.chat_repo.create_session(
                user_id=current_user.id,
                document_id=document.id,
            )
        except Exception:
            self.db.rollback()
            raise

    def list_sessions(
        self, *, current_user: User, limit: int, offset: int,
    ) -> ChatSessionListResponse:
        return ChatSessionListResponse(
            items=[
                ChatSessionResponse.model_validate(session)
                for session in self.chat_repo.list_owned_sessions(
                    user_id=current_user.id, limit=limit, offset=offset,
                )
            ],
            total=self.chat_repo.count_owned_sessions(user_id=current_user.id),
            limit=limit,
            offset=offset,
        )

    def list_sessions_for_document(
        self,
        *,
        document_id: uuid.UUID,
        current_user: User,
    ) -> list[ChatSession]:
        return self.chat_repo.list_owned_sessions_by_document(
            document_id=document_id,
            user_id=current_user.id,
        )

    def delete_session(
        self,
        *,
        session_id: uuid.UUID,
        current_user: User,
    ) -> None:
        try:
            deleted = self.chat_repo.delete_owned_session(
                session_id=session_id, user_id=current_user.id,
            )
            if not deleted:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Khong tim thay phien chat.",
                )
        except Exception:
            self.db.rollback()
            raise

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
        # Capture the actor before any rollback expires authentication objects.
        user_id = current_user.id
        try:
            session = self._get_writable_session(session_id, user_id)
            document_id = session.document_id
            assert document_id is not None  # checked by _get_writable_session
            # The provider only consumes role/content. Transient snapshots
            # prevent ORM refreshes from opening a transaction during the LLM call.
            history = [
                ChatMessage(role=message.role, content=message.content)
                for message in self.chat_repo.list_messages(session_id=session_id)[-6:]
            ]
            self.chat_repo.add_message(
                session_id=session_id,
                role="user",
                content=content,
                source_chunks=None,
            )
            self.db.rollback()  # add_message refreshes; release that read transaction.
            try:
                chunks = self.retriever.retrieve(
                    document_id=document_id,
                    question=content,
                    top_k=5,
                )
            finally:
                self.db.rollback()
            if not chunks:
                return self._save_answer(session_id, user_id, REFUSAL_ANSWER, [])

            # Deletion may have completed during retrieval. Recheck, then drop
            # every DB lock before calling the provider.
            self._get_writable_session(session_id, user_id)
            self.db.rollback()
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
                return self._save_answer(session_id, user_id, REFUSAL_ANSWER, [])

            selected_indexes = set(generated.source_chunk_indexes)
            selected_chunks = [
                chunk for chunk in chunks
                if generated.grounded and chunk.chunk_index in selected_indexes
            ]
            citations = [
                ChatCitation(
                    chunk_id=chunk.chunk_id,
                    chunk_index=chunk.chunk_index,
                    quote=chunk.content,
                    score=chunk.score,
                    heading_path=chunk.heading_path,
                )
                for chunk in selected_chunks
            ]
            return self._save_answer(session_id, user_id, generated.content, citations)
        finally:
            self.db.rollback()

    def _get_writable_session(
        self, session_id: uuid.UUID, user_id: uuid.UUID,
    ) -> ChatSession:
        session = self._get_owned_session(session_id, user_id)
        document_id = session.document_id
        if document_id is None:
            self._raise_deleted_document()
        # Lock in the same order as DELETE: document before chat session. The
        # FK's SET NULL can otherwise deadlock against a session-first lock.
        document = self.document_repo.get_for_update(document_id)
        locked_session = self.chat_repo.get_owned_session(
            session_id=session_id, user_id=user_id, for_update=True,
        )
        if locked_session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Khong tim thay phien chat.",
            )
        if document is None or locked_session.document_id is None:
            self._raise_deleted_document()
        return locked_session

    @staticmethod
    def _raise_deleted_document() -> NoReturn:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Tai lieu cua phien chat da bi xoa. Phien chat chi co the doc.",
        )

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
        user_id: uuid.UUID,
        answer: str,
        sources: list[ChatCitation],
    ) -> ChatAnswerResponse:
        # An answer generated concurrently with document/session deletion must
        # not write into a now read-only (or deleted) conversation.
        self._get_writable_session(session_id, user_id)
        source_rows = [source.model_dump(mode="json") for source in sources]
        self.chat_repo.add_message(
            session_id=session_id,
            role="assistant",
            content=answer,
            source_chunks=source_rows,
        )
        return ChatAnswerResponse(answer=answer, sources=sources)

    @staticmethod
    def _message_response(message: ChatMessage) -> ChatMessageResponse:
        return ChatMessageResponse.model_validate({
            "id": message.id,
            "role": message.role,
            "content": message.content,
            "sources": message.source_chunks or [],
            "created_at": message.created_at,
        })
