import os
import unittest
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ["DATABASE_URL"] = "sqlite://"

from app.api.routers.chat import get_answer_provider, get_retriever
from app.core.database import Base, get_db
from app.core.security import create_access_token
from app.main import app
from app.models.chat import ChatMessage, ChatSession
from app.models.document import Document, DocumentChunk, ProcessingStatus
from app.models.folder import Folder
from app.models.user import User, UserRole
from app.schemas.retrieval import RetrievedChunk
from app.services.gemini_provider import GeneratedAnswer


class FakeRetriever:
    def __init__(self):
        self.calls = []

    def retrieve(self, *, document_id, question, top_k=5):
        self.calls.append((document_id, question, top_k))
        return [
            RetrievedChunk(
                chunk_id=uuid.uuid4(),
                document_id=document_id,
                chunk_index=0,
                content="FastAPI dung de xay dung API.",
                score=0.9,
            )
        ]


class FakeProvider:
    def answer(self, *, question, context, history):
        return GeneratedAnswer(
            content="FastAPI dung de xay dung API.",
            grounded=True,
        )


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


class ChatAPITestCase(unittest.TestCase):
    def setUp(self):
        self.previous_overrides = dict(app.dependency_overrides)
        self.retriever = FakeRetriever()
        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_retriever] = lambda: self.retriever
        app.dependency_overrides[get_answer_provider] = lambda: FakeProvider()
        self.client = TestClient(app)

        db = TestingSessionLocal()
        db.query(ChatMessage).delete()
        db.query(ChatSession).delete()
        db.query(DocumentChunk).delete()
        db.query(Document).delete()
        db.query(User).delete()
        db.commit()
        db.close()

        self.student = self.create_user("student@example.com", UserRole.STUDENT)
        self.teacher = self.create_user("teacher@example.com", UserRole.TEACHER)
        self.other = self.create_user("other@example.com", UserRole.STUDENT)
        self.document = self.create_ready_document(self.teacher.id)
        self.student_headers = self.headers(self.student)
        self.teacher_headers = self.headers(self.teacher)
        self.other_headers = self.headers(self.other)

    def tearDown(self):
        app.dependency_overrides.clear()
        app.dependency_overrides.update(self.previous_overrides)

    @staticmethod
    def headers(user: User) -> dict[str, str]:
        token = create_access_token(str(user.id), user.role.value)
        return {"Authorization": f"Bearer {token}"}

    @staticmethod
    def create_user(email: str, role: UserRole) -> User:
        db = TestingSessionLocal()
        user = User(
            full_name=email.split("@")[0],
            email=email,
            hashed_password="not-used",
            role=role,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        db.expunge(user)
        db.close()
        return user

    @staticmethod
    def create_ready_document(uploaded_by: uuid.UUID) -> Document:
        db = TestingSessionLocal()
        document = Document(
            title="FastAPI",
            file_path="/app/uploads/fastapi.txt",
            file_type="txt",
            uploaded_by=uploaded_by,
            processing_status=ProcessingStatus.DONE,
        )
        db.add(document)
        db.commit()
        db.refresh(document)
        db.add(
            DocumentChunk(
                document_id=document.id,
                chunk_index=0,
                content="FastAPI dung de xay dung API.",
                embedding=[1.0] + [0.0] * 383,
            )
        )
        db.commit()
        db.refresh(document)
        db.expunge(document)
        db.close()
        return document

    def create_session(self, headers=None) -> dict:
        response = self.client.post(
            "/chat/sessions",
            headers=headers or self.student_headers,
            json={"document_id": str(self.document.id)},
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_create_session_requires_token_and_allows_student_and_teacher(self):
        unauthenticated = self.client.post(
            "/chat/sessions",
            json={"document_id": str(self.document.id)},
        )
        self.assertEqual(unauthenticated.status_code, 401)

        for headers in (self.student_headers, self.teacher_headers):
            with self.subTest(headers=headers):
                response = self.client.post(
                    "/chat/sessions",
                    headers=headers,
                    json={"document_id": str(self.document.id)},
                )
                self.assertEqual(response.status_code, 201, response.text)
                self.assertEqual(response.json()["document_id"], str(self.document.id))

    def test_session_is_private_for_get_and_message(self):
        session = self.create_session()

        hidden = self.client.get(
            f"/chat/sessions/{session['id']}",
            headers=self.other_headers,
        )
        forbidden_message = self.client.post(
            f"/chat/sessions/{session['id']}/messages",
            headers=self.other_headers,
            json={"content": "Cau hoi"},
        )

        self.assertEqual(hidden.status_code, 404)
        self.assertEqual(forbidden_message.status_code, 404)

    def test_message_validation_rejects_empty_and_document_switch(self):
        session = self.create_session()

        empty = self.client.post(
            f"/chat/sessions/{session['id']}/messages",
            headers=self.student_headers,
            json={"content": "   "},
        )
        switched = self.client.post(
            f"/chat/sessions/{session['id']}/messages",
            headers=self.student_headers,
            json={"content": "Cau hoi", "document_id": str(uuid.uuid4())},
        )

        self.assertEqual(empty.status_code, 422)
        self.assertEqual(switched.status_code, 422)

    def test_ask_returns_sources_and_history_maps_persisted_citations(self):
        session = self.create_session()

        answer = self.client.post(
            f"/chat/sessions/{session['id']}/messages",
            headers=self.student_headers,
            json={"content": "FastAPI dung de lam gi?"},
        )

        self.assertEqual(answer.status_code, 201, answer.text)
        self.assertEqual(answer.json()["answer"], "FastAPI dung de xay dung API.")
        self.assertEqual(len(answer.json()["sources"]), 1)
        self.assertEqual(self.retriever.calls[0][0], self.document.id)

        detail = self.client.get(
            f"/chat/sessions/{session['id']}",
            headers=self.student_headers,
        )
        self.assertEqual(detail.status_code, 200, detail.text)
        messages = detail.json()["messages"]
        self.assertEqual([message["role"] for message in messages], ["user", "assistant"])
        self.assertEqual(messages[0]["sources"], [])
        self.assertEqual(len(messages[1]["sources"]), 1)


if __name__ == "__main__":
    unittest.main()
