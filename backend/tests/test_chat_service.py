import os
import unittest
import uuid

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ["DATABASE_URL"] = "sqlite://"

from app.core.database import Base
from app.models.chat import ChatMessage, ChatSession
from app.models.document import Document, DocumentChunk, ProcessingStatus
from app.models.folder import Folder
from app.models.user import User, UserRole
from app.schemas.retrieval import RetrievedChunk
from app.services.chat_service import REFUSAL_ANSWER, ChatService
from app.services.gemini_provider import GeneratedAnswer, GeminiProviderError


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)


class FakeRetriever:
    def __init__(self, chunks):
        self.chunks = chunks
        self.calls = []

    def retrieve(self, *, document_id, question, top_k=5):
        self.calls.append((document_id, question, top_k))
        return self.chunks


class FakeProvider:
    def __init__(self, answer=None, error=None):
        self.answer_value = answer
        self.error = error
        self.calls = []

    def answer(self, *, question, context, history):
        self.calls.append((question, context, history))
        if self.error:
            raise self.error
        return self.answer_value


class ChatServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.db = TestingSessionLocal()
        self.db.query(ChatMessage).delete()
        self.db.query(ChatSession).delete()
        self.db.query(DocumentChunk).delete()
        self.db.query(Document).delete()
        self.db.query(User).delete()
        self.db.commit()
        self.user = User(
            full_name="Student",
            email="student@example.com",
            hashed_password="not-used",
            role=UserRole.STUDENT,
            is_active=True,
        )
        self.db.add(self.user)
        self.db.commit()
        self.db.refresh(self.user)

    def tearDown(self):
        self.db.close()

    def create_document(
        self,
        status: ProcessingStatus,
        *,
        with_chunk: bool = False,
    ) -> Document:
        document = Document(
            title=f"Document {status.value}",
            file_path=f"/app/uploads/{uuid.uuid4()}.txt",
            file_type="txt",
            uploaded_by=self.user.id,
            processing_status=status,
        )
        self.db.add(document)
        self.db.commit()
        self.db.refresh(document)
        if with_chunk:
            self.db.add(
                DocumentChunk(
                    document_id=document.id,
                    chunk_index=0,
                    content="Bien la vung nho dung de luu du lieu. " + "x" * 220,
                    embedding=[1.0] + [0.0] * 383,
                )
            )
            self.db.commit()
        return document

    def service(self, chunks=None, answer=None, error=None):
        retriever = FakeRetriever(chunks or [])
        provider = FakeProvider(answer=answer, error=error)
        return ChatService(self.db, retriever, provider), retriever, provider

    def test_create_session_requires_existing_ready_document_with_embedding(self):
        service, _, _ = self.service()

        with self.assertRaises(HTTPException) as missing:
            service.create_session(document_id=uuid.uuid4(), current_user=self.user)
        self.assertEqual(missing.exception.status_code, 404)

        for status in (
            ProcessingStatus.PENDING,
            ProcessingStatus.PROCESSING,
            ProcessingStatus.FAILED,
        ):
            with self.subTest(status=status):
                document = self.create_document(status)
                with self.assertRaises(HTTPException) as not_ready:
                    service.create_session(document_id=document.id, current_user=self.user)
                self.assertEqual(not_ready.exception.status_code, 409)

        done_without_chunk = self.create_document(ProcessingStatus.DONE)
        with self.assertRaises(HTTPException) as no_content:
            service.create_session(
                document_id=done_without_chunk.id,
                current_user=self.user,
            )
        self.assertEqual(no_content.exception.status_code, 409)

        ready = self.create_document(ProcessingStatus.DONE, with_chunk=True)
        session = service.create_session(document_id=ready.id, current_user=self.user)
        self.assertEqual(session.user_id, self.user.id)
        self.assertEqual(session.document_id, ready.id)

    def test_ask_builds_readable_bounded_quote_and_persists_it(self):
        document = self.create_document(ProcessingStatus.DONE, with_chunk=True)
        retrieved = RetrievedChunk(
            chunk_id=uuid.uuid4(),
            document_id=document.id,
            chunk_index=0,
            content=(
                "[TABLE 4]" + chr(10)
                + "Mức: P1 - Critical; Thời gian phản hồi: 30 phút" + chr(10)
                + "Mức: P2 - High; Thời gian phản hồi: 4 giờ" + chr(10)
                + "Chi tiết bổ sung: "
                + "a" * 500
            ),
            score=0.82,
        )
        service, retriever, provider = self.service(
            chunks=[retrieved],
            answer=GeneratedAnswer(content="Bien dung de luu du lieu.", grounded=True),
        )
        session = service.create_session(document_id=document.id, current_user=self.user)

        response = service.ask(
            session_id=session.id,
            content="Bien la gi?",
            current_user=self.user,
        )

        self.assertEqual(retriever.calls, [(document.id, "Bien la gi?", 5)])
        self.assertEqual(len(provider.calls), 1)
        self.assertEqual(provider.calls[0][2], [])
        self.assertEqual(response.answer, "Bien dung de luu du lieu.")
        self.assertEqual(len(response.sources), 1)
        self.assertEqual(response.sources[0].chunk_id, retrieved.chunk_id)
        self.assertLessEqual(len(response.sources[0].quote), 400)
        self.assertNotIn("\n", response.sources[0].quote)
        self.assertNotIn("  ", response.sources[0].quote)
        self.assertTrue(response.sources[0].quote.endswith("…"))
        self.assertIn("Mức: P1", response.sources[0].quote)
        self.assertIn("Mức: P2", response.sources[0].quote)
        messages = self.db.query(ChatMessage).order_by(ChatMessage.created_at).all()
        self.assertEqual([message.role for message in messages], ["user", "assistant"])
        self.assertEqual(messages[1].source_chunks[0]["chunk_id"], str(retrieved.chunk_id))

    def test_empty_or_ungrounded_context_returns_refusal_without_sources(self):
        document = self.create_document(ProcessingStatus.DONE, with_chunk=True)
        service, _, provider = self.service()
        session = service.create_session(document_id=document.id, current_user=self.user)

        empty_response = service.ask(
            session_id=session.id,
            content="Cau hoi ngoai tai lieu",
            current_user=self.user,
        )
        self.assertEqual(empty_response.answer, REFUSAL_ANSWER)
        self.assertEqual(empty_response.sources, [])
        self.assertEqual(provider.calls, [])

        retrieved = RetrievedChunk(
            chunk_id=uuid.uuid4(),
            document_id=document.id,
            chunk_index=0,
            content="Noi dung khong du.",
            score=0.1,
        )
        service, _, _ = self.service(
            chunks=[retrieved],
            answer=GeneratedAnswer(content="Noi dung tu do", grounded=False),
        )
        another_session = service.create_session(
            document_id=document.id,
            current_user=self.user,
        )
        ungrounded = service.ask(
            session_id=another_session.id,
            content="Cau hoi khac",
            current_user=self.user,
        )
        self.assertEqual(ungrounded.answer, REFUSAL_ANSWER)
        self.assertEqual(ungrounded.sources, [])

    def test_ask_refuses_when_retriever_returns_no_qualifying_chunks(self):
        document = self.create_document(ProcessingStatus.DONE, with_chunk=True)
        service, _, provider = self.service(
            chunks=[],
            answer=GeneratedAnswer(content="Khong nen duoc goi", grounded=True),
        )
        session = service.create_session(document_id=document.id, current_user=self.user)

        response = service.ask(
            session_id=session.id,
            content="PDF toi da bao nhieu MB?",
            current_user=self.user,
        )

        self.assertEqual(response.answer, REFUSAL_ANSWER)
        self.assertEqual(response.sources, [])
        self.assertEqual(provider.calls, [])

    def test_provider_failure_returns_503_without_assistant_message(self):
        document = self.create_document(ProcessingStatus.DONE, with_chunk=True)
        retrieved = RetrievedChunk(
            chunk_id=uuid.uuid4(),
            document_id=document.id,
            chunk_index=0,
            content="Noi dung",
            score=0.8,
        )
        service, _, _ = self.service(
            chunks=[retrieved],
            error=GeminiProviderError("quota"),
        )
        session = service.create_session(document_id=document.id, current_user=self.user)

        with self.assertRaises(HTTPException) as provider_error:
            service.ask(
                session_id=session.id,
                content="Cau hoi",
                current_user=self.user,
            )

        self.assertEqual(provider_error.exception.status_code, 503)
        messages = self.db.query(ChatMessage).all()
        self.assertEqual([message.role for message in messages], ["user"])


if __name__ == "__main__":
    unittest.main()
