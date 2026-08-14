import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permissions import Permission
from app.core.security import require_permission
from app.schemas.chat import (
    ChatAnswerResponse,
    ChatQuestionRequest,
    ChatSessionCreate,
    ChatSessionDetailResponse,
    ChatSessionResponse,
)
from app.services.chat_service import ChatService
from app.services.gemini_provider import GeminiProvider


router = APIRouter(prefix="/chat", tags=["Chat with Documents"])
chat_user = require_permission(Permission.USE_CHAT)


def get_retriever(db: Session = Depends(get_db)):
    from app.services.retrieval_service import RetrievalService

    return RetrievalService(db)


def get_answer_provider():
    provider = GeminiProvider()
    try:
        yield provider
    finally:
        provider.close()


def get_chat_service(
    db: Session = Depends(get_db),
    retriever=Depends(get_retriever),
    provider=Depends(get_answer_provider),
) -> ChatService:
    return ChatService(db, retriever, provider)


@router.post(
    "/sessions",
    response_model=ChatSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_session(
    data: ChatSessionCreate,
    current_user=Depends(chat_user),
    service: ChatService = Depends(get_chat_service),
):
    return service.create_session(
        document_id=data.document_id,
        current_user=current_user,
    )


@router.get(
    "/documents/{document_id}/sessions",
    response_model=list[ChatSessionResponse],
)
def list_document_sessions(
    document_id: uuid.UUID,
    current_user=Depends(chat_user),
    service: ChatService = Depends(get_chat_service),
):
    return service.list_sessions_for_document(
        document_id=document_id,
        current_user=current_user,
    )


@router.get(
    "/sessions/{session_id}",
    response_model=ChatSessionDetailResponse,
)
def get_session(
    session_id: uuid.UUID,
    current_user=Depends(chat_user),
    service: ChatService = Depends(get_chat_service),
):
    return service.get_session(
        session_id=session_id,
        current_user=current_user,
    )


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_session(
    session_id: uuid.UUID,
    current_user=Depends(chat_user),
    service: ChatService = Depends(get_chat_service),
):
    service.delete_session(
        session_id=session_id,
        current_user=current_user,
    )


@router.post(
    "/sessions/{session_id}/messages",
    response_model=ChatAnswerResponse,
    status_code=status.HTTP_201_CREATED,
)
def ask_question(
    session_id: uuid.UUID,
    data: ChatQuestionRequest,
    current_user=Depends(chat_user),
    service: ChatService = Depends(get_chat_service),
):
    return service.ask(
        session_id=session_id,
        content=data.content,
        current_user=current_user,
    )
