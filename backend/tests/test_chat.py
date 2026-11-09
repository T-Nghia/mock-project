import os
import unittest
import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ["DATABASE_URL"] = "sqlite://"

from app.api.routers.chat import get_answer_provider, get_retriever
from app.core.database import Base, get_db
from app.core.security import create_access_token
from app.main import app
from app.models.chat import ChatMessage, ChatSession
from app.models.document import Document, DocumentChunk, ProcessingStatus
from app.models.folder import Folder  # noqa: F401 - register foreign-key table
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
                heading_path=[],
            )
        ]


class FakeProvider:
    def __init__(self):
        self.calls = []

    def answer(self, *, question, context, history):
        self.calls.append((question, context, history))
        return GeneratedAnswer(
            content="FastAPI dung de xay dung API.",
            grounded=True,
            source_chunk_indexes=[0],
        )


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@event.listens_for(engine, "connect")
def enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
    dbapi_connection.execute("PRAGMA foreign_keys=ON")


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
        self.provider = FakeProvider()
        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_retriever] = lambda: self.retriever
        app.dependency_overrides[get_answer_provider] = lambda: self.provider
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

    def create_session_for(self, user: User) -> dict:
        return self.create_session(self.headers(user))

    def create_legacy_orphan(self, user: User) -> tuple[str, list[dict]]:
        """An orphan which already existed before the new deletion service."""
        sources = [{
            "chunk_id": str(uuid.uuid4()), "chunk_index": 3,
            "quote": "Preserved citation snapshot", "score": 0.9,
            "heading_path": ["Old section"],
        }]
        with TestingSessionLocal() as db:
            session = ChatSession(user_id=user.id, document_id=None, title="Old chat")
            db.add(session)
            db.flush()
            session_id = str(session.id)
            db.add_all([
                ChatMessage(session_id=session.id, role="user", content="Old question"),
                ChatMessage(
                    session_id=session.id, role="assistant", content="Old answer",
                    source_chunks=sources,
                ),
            ])
            db.commit()
        return session_id, sources

    def test_history_list_is_paginated_owned_and_includes_legacy_orphans(self):
        live = self.create_session()
        orphan_id, _ = self.create_legacy_orphan(self.student)
        self.create_legacy_orphan(self.other)

        unauthenticated = self.client.get("/chat/sessions")
        self.assertEqual(unauthenticated.status_code, 401)
        first = self.client.get(
            "/chat/sessions?limit=1&offset=0", headers=self.student_headers,
        )
        second = self.client.get(
            "/chat/sessions?limit=1&offset=1", headers=self.student_headers,
        )
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(first.json()["total"], 2)
        self.assertEqual(first.json()["limit"], 1)
        self.assertEqual(first.json()["offset"], 0)
        items = first.json()["items"] + second.json()["items"]
        self.assertEqual({item["id"] for item in items}, {live["id"], orphan_id})
        orphan = next(item for item in items if item["id"] == orphan_id)
        self.assertIsNone(orphan["document_id"])
        empty = self.client.get(
            "/chat/sessions?offset=2", headers=self.student_headers,
        )
        self.assertEqual(empty.json()["items"], [])
        self.assertEqual(empty.json()["total"], 2)

    def test_history_pagination_rejects_invalid_bounds(self):
        for query in ("limit=0", "limit=101", "offset=-1", "limit=bad"):
            with self.subTest(query=query):
                response = self.client.get(
                    f"/chat/sessions?{query}", headers=self.student_headers,
                )
                self.assertEqual(response.status_code, 422)

    def test_legacy_orphan_transcript_keeps_messages_and_citation_snapshot(self):
        orphan_id, sources = self.create_legacy_orphan(self.student)
        response = self.client.get(
            f"/chat/sessions/{orphan_id}", headers=self.student_headers,
        )
        self.assertEqual(response.status_code, 200, response.text)
        detail = response.json()
        self.assertIsNone(detail["document_id"])
        self.assertEqual(len(detail["messages"]), 2)
        assistant = next(message for message in detail["messages"] if message["role"] == "assistant")
        self.assertEqual(assistant["sources"], sources)
        hidden = self.client.get(
            f"/chat/sessions/{orphan_id}", headers=self.other_headers,
        )
        self.assertEqual(hidden.status_code, 404)

    def test_orphan_message_returns_409_without_provider_retriever_or_write(self):
        orphan_id, _ = self.create_legacy_orphan(self.student)
        response = self.client.post(
            f"/chat/sessions/{orphan_id}/messages", headers=self.student_headers,
            json={"content": "Cannot ask this"},
        )
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(self.retriever.calls, [])
        self.assertEqual(self.provider.calls, [])
        with TestingSessionLocal() as db:
            self.assertEqual(db.query(ChatMessage).count(), 2)

    def test_orphan_delete_is_private_cascades_messages_and_repeated_delete_is_404(self):
        orphan_id, _ = self.create_legacy_orphan(self.student)
        hidden = self.client.delete(
            f"/chat/sessions/{orphan_id}", headers=self.other_headers,
        )
        self.assertEqual(hidden.status_code, 404)
        deleted = self.client.delete(
            f"/chat/sessions/{orphan_id}", headers=self.student_headers,
        )
        self.assertEqual(deleted.status_code, 204, deleted.text)
        self.assertEqual(deleted.content, b"")
        repeated = self.client.delete(
            f"/chat/sessions/{orphan_id}", headers=self.student_headers,
        )
        self.assertEqual(repeated.status_code, 404)
        with TestingSessionLocal() as db:
            self.assertIsNone(db.get(ChatSession, uuid.UUID(orphan_id)))
            self.assertEqual(db.query(ChatMessage).count(), 0)

    def test_document_fk_set_null_keeps_history_readable(self):
        session = self.create_session()
        answer = self.client.post(
            f"/chat/sessions/{session['id']}/messages", headers=self.student_headers,
            json={"content": "Original question"},
        )
        self.assertEqual(answer.status_code, 201, answer.text)
        old_messages = self.client.get(
            f"/chat/sessions/{session['id']}", headers=self.student_headers,
        ).json()["messages"]
        with TestingSessionLocal() as db:
            db.delete(db.get(Document, self.document.id))
            db.commit()
        response = self.client.get(
            f"/chat/sessions/{session['id']}", headers=self.student_headers,
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIsNone(response.json()["document_id"])
        self.assertEqual(response.json()["messages"], old_messages)

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

    def test_list_document_sessions_requires_token(self):
        response = self.client.get(f"/chat/documents/{self.document.id}/sessions")

        self.assertEqual(response.status_code, 401)

    def test_list_document_sessions_returns_current_users_sessions_newest_first(self):
        first = self.create_session_for(self.student)
        second = self.create_session_for(self.student)
        self.create_session_for(self.other)

        db = TestingSessionLocal()
        first_row = db.get(ChatSession, uuid.UUID(first["id"]))
        second_row = db.get(ChatSession, uuid.UUID(second["id"]))
        first_row.created_at = datetime(2026, 8, 14, 10, 0, tzinfo=timezone.utc)
        second_row.created_at = datetime(2026, 8, 14, 10, 1, tzinfo=timezone.utc)
        db.commit()
        db.close()

        response = self.client.get(
            f"/chat/documents/{self.document.id}/sessions",
            headers=self.student_headers,
        )

        self.assertEqual(response.status_code, 200, response.text)
        sessions = response.json()
        self.assertEqual([session["id"] for session in sessions], [second["id"], first["id"]])
        self.assertTrue(all(session["document_id"] == str(self.document.id) for session in sessions))
        self.assertTrue(
            all(set(session) == {"id", "document_id", "title", "created_at"} for session in sessions)
        )

    def test_list_document_sessions_returns_empty_array_when_user_has_no_sessions(self):
        response = self.client.get(
            f"/chat/documents/{self.document.id}/sessions",
            headers=self.student_headers,
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), [])

    def test_delete_session_requires_token(self):
        session = self.create_session()

        response = self.client.delete(f"/chat/sessions/{session['id']}")

        self.assertEqual(response.status_code, 401)

    def test_owner_can_delete_session_and_messages_are_cascaded(self):
        session = self.create_session()
        other_session = self.create_session()

        db = TestingSessionLocal()
        db.add_all(
            [
                ChatMessage(
                    session_id=uuid.UUID(session["id"]),
                    role="user",
                    content="Question",
                ),
                ChatMessage(
                    session_id=uuid.UUID(session["id"]),
                    role="assistant",
                    content="Answer",
                    source_chunks=[],
                ),
            ]
        )
        db.commit()
        db.close()

        response = self.client.delete(
            f"/chat/sessions/{session['id']}",
            headers=self.student_headers,
        )

        self.assertEqual(response.status_code, 204, response.text)
        self.assertEqual(response.content, b"")

        db = TestingSessionLocal()
        self.assertIsNone(db.get(ChatSession, uuid.UUID(session["id"])))
        self.assertEqual(
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == uuid.UUID(session["id"]))
            .count(),
            0,
        )
        self.assertIsNotNone(db.get(ChatSession, uuid.UUID(other_session["id"])))
        db.close()

    def test_other_user_cannot_delete_session(self):
        session = self.create_session()

        response = self.client.delete(
            f"/chat/sessions/{session['id']}",
            headers=self.other_headers,
        )

        self.assertEqual(response.status_code, 404)
        db = TestingSessionLocal()
        self.assertIsNotNone(db.get(ChatSession, uuid.UUID(session["id"])))
        db.close()

    def test_delete_missing_session_returns_not_found(self):
        response = self.client.delete(
            f"/chat/sessions/{uuid.uuid4()}",
            headers=self.student_headers,
        )

        self.assertEqual(response.status_code, 404)

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
