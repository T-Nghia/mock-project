import os
import unittest
import uuid
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ["DATABASE_URL"] = "sqlite://"

from app.core.database import Base
from app.models.chat import ChatMessage, ChatSession
from app.models.document import Document, ProcessingStatus
from app.models.folder import Folder  # noqa: F401 - register foreign-key table
from app.models.user import User, UserRole
from app.repositories.chat_repo import ChatRepository


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)


class ChatRepositoryTestCase(unittest.TestCase):
    def setUp(self):
        self.db = TestingSessionLocal()
        self.db.query(ChatMessage).delete()
        self.db.query(ChatSession).delete()
        self.db.query(Document).delete()
        self.db.query(User).delete()
        self.db.commit()

        self.user_a = self.create_user("a@example.com")
        self.user_b = self.create_user("b@example.com")
        self.document = Document(
            title="Python",
            file_path="/app/uploads/python.txt",
            file_type="txt",
            uploaded_by=self.user_a.id,
            processing_status=ProcessingStatus.DONE,
        )
        self.db.add(self.document)
        self.db.commit()
        self.db.refresh(self.document)
        self.repo = ChatRepository(self.db)

    def tearDown(self):
        self.db.close()

    def create_user(self, email: str) -> User:
        user = User(
            full_name=email.split("@")[0],
            email=email,
            hashed_password="not-used",
            role=UserRole.STUDENT,
            is_active=True,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def test_session_lookup_is_scoped_to_owner(self):
        session = self.repo.create_session(
            user_id=self.user_a.id,
            document_id=self.document.id,
        )

        owned = self.repo.get_owned_session(
            session_id=session.id,
            user_id=self.user_a.id,
        )
        hidden = self.repo.get_owned_session(
            session_id=session.id,
            user_id=self.user_b.id,
        )

        self.assertEqual(owned.id, session.id)
        self.assertIsNone(hidden)

    def test_list_owned_sessions_by_document_filters_owner_and_document(self):
        other_document = Document(
            title="SQLAlchemy",
            file_path="/app/uploads/sqlalchemy.txt",
            file_type="txt",
            uploaded_by=self.user_a.id,
            processing_status=ProcessingStatus.DONE,
        )
        self.db.add(other_document)
        self.db.commit()

        expected = self.repo.create_session(
            user_id=self.user_a.id,
            document_id=self.document.id,
        )
        self.repo.create_session(
            user_id=self.user_b.id,
            document_id=self.document.id,
        )
        self.repo.create_session(
            user_id=self.user_a.id,
            document_id=other_document.id,
        )

        sessions = self.repo.list_owned_sessions_by_document(
            user_id=self.user_a.id,
            document_id=self.document.id,
        )

        self.assertEqual([session.id for session in sessions], [expected.id])

    def test_list_owned_sessions_by_document_orders_newest_first(self):
        older = self.repo.create_session(
            user_id=self.user_a.id,
            document_id=self.document.id,
        )
        newer = self.repo.create_session(
            user_id=self.user_a.id,
            document_id=self.document.id,
        )
        older.created_at = datetime(2026, 8, 14, 10, 0, tzinfo=timezone.utc)
        newer.created_at = datetime(2026, 8, 14, 10, 1, tzinfo=timezone.utc)
        self.db.commit()

        sessions = self.repo.list_owned_sessions_by_document(
            user_id=self.user_a.id,
            document_id=self.document.id,
        )

        self.assertEqual([session.id for session in sessions], [newer.id, older.id])

    def test_messages_are_ordered_and_citations_are_persisted(self):
        session = self.repo.create_session(
            user_id=self.user_a.id,
            document_id=self.document.id,
        )
        chunk_id = uuid.uuid4()
        self.repo.add_message(
            session_id=session.id,
            role="user",
            content="Bien la gi?",
        )
        self.repo.add_message(
            session_id=session.id,
            role="assistant",
            content="Bien la vung nho.",
            source_chunks=[
                {
                    "chunk_id": str(chunk_id),
                    "chunk_index": 2,
                    "quote": "Bien la vung nho.",
                    "score": 0.82,
                }
            ],
        )

        messages = self.repo.list_messages(session_id=session.id)

        self.assertEqual([message.role for message in messages], ["user", "assistant"])
        self.assertIsNone(messages[0].source_chunks)
        self.assertEqual(messages[1].source_chunks[0]["chunk_id"], str(chunk_id))
        self.assertEqual(messages[1].source_chunks[0]["score"], 0.82)


if __name__ == "__main__":
    unittest.main()
