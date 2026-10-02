import os
import unittest
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ["DATABASE_URL"] = "sqlite://"

from app.core.database import Base, get_db
from app.core.security import hash_password
from app.main import app
from app.models.document import Document, ProcessingStatus
from app.models.folder import Folder
from app.models.user import User, UserRole
from app.services import auth_service


class FakeRedis:
    def __init__(self):
        self.store = {}

    def setex(self, key, ttl, value):
        self.store[key] = value

    def get(self, key):
        return self.store.get(key)

    def delete(self, key):
        self.store.pop(key, None)


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


class DashboardAPITestCase(unittest.TestCase):
    def setUp(self):
        self.previous_db_override = app.dependency_overrides.get(get_db)
        app.dependency_overrides[get_db] = override_get_db
        auth_service.redis_client = FakeRedis()
        self.client = TestClient(app)

        db = TestingSessionLocal()
        db.query(Document).delete()
        db.query(Folder).delete()
        db.query(User).delete()
        db.commit()
        db.close()

        self.admin = self.create_user("admin@example.com", UserRole.ADMIN)
        self.teacher = self.create_user("teacher@example.com", UserRole.TEACHER)
        self.student = self.create_user("student@example.com", UserRole.STUDENT)
        self.admin_headers = self.login_headers("admin@example.com")
        self.teacher_headers = self.login_headers("teacher@example.com")
        self.student_headers = self.login_headers("student@example.com")
        self.seed_documents()

    def tearDown(self):
        if self.previous_db_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = self.previous_db_override

    @staticmethod
    def create_user(email: str, role: UserRole) -> User:
        db = TestingSessionLocal()
        user = User(
            full_name=email.split("@")[0],
            email=email,
            hashed_password=hash_password("Password@123"),
            role=role,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        db.expunge(user)
        db.close()
        return user

    def login_headers(self, email: str) -> dict[str, str]:
        response = self.client.post(
            "/auth/login",
            json={"email": email, "password": "Password@123"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def seed_documents(self):
        now = datetime.now(timezone.utc)
        db = TestingSessionLocal()
        python = Folder(name="Python", owner_id=self.teacher.id)
        web = Folder(name="Web", owner_id=self.teacher.id)
        db.add_all([python, web])
        db.flush()
        db.add_all(
            [
                Document(
                    title="Python basics",
                    file_path="/app/uploads/python.pdf",
                    file_type="pdf",
                    folder_id=python.id,
                    uploaded_by=self.teacher.id,
                    processing_status=ProcessingStatus.DONE,
                    created_at=now,
                ),
                Document(
                    title="Unfiled teacher document",
                    file_path="/app/uploads/unfiled.pdf",
                    file_type="pdf",
                    uploaded_by=self.teacher.id,
                    processing_status=ProcessingStatus.DONE,
                    created_at=now - timedelta(days=1),
                ),
                Document(
                    title="Admin web document",
                    file_path="/app/uploads/web.pdf",
                    file_type="pdf",
                    folder_id=web.id,
                    uploaded_by=self.admin.id,
                    processing_status=ProcessingStatus.DONE,
                    created_at=now,
                ),
            ]
        )
        db.commit()
        db.close()

    def test_dashboard_requires_access_token(self):
        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 401)

    def test_admin_receives_system_metrics_and_charts(self):
        response = self.client.get("/dashboard", headers=self.admin_headers)

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["role"], "admin")
        self.assertEqual(payload["summary"], {"total_documents": 3, "total_users": 3})
        self.assertEqual(len(payload["charts"]["uploads_by_day"]), 7)
        self.assertEqual(
            sum(point["count"] for point in payload["charts"]["uploads_by_day"]),
            3,
        )
        self.assertEqual(
            payload["charts"]["documents_by_folder"],
            [
                {"label": "Python", "count": 1},
                {"label": "Uncategorized", "count": 1},
                {"label": "Web", "count": 1},
            ],
        )
        self.assertEqual(
            payload["charts"]["users_by_role"],
            [
                {"label": "admin", "count": 1},
                {"label": "student", "count": 1},
                {"label": "teacher", "count": 1},
            ],
        )

    def test_teacher_receives_only_own_document_metrics(self):
        response = self.client.get("/dashboard", headers=self.teacher_headers)

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["role"], "teacher")
        self.assertEqual(payload["summary"], {"total_documents": 2})
        self.assertNotIn("total_users", payload["summary"])
        self.assertNotIn("users_by_role", payload["charts"])
        self.assertEqual(
            sum(point["count"] for point in payload["charts"]["uploads_by_day"]),
            2,
        )
        self.assertEqual(
            payload["charts"]["documents_by_folder"],
            [
                {"label": "Python", "count": 1},
                {"label": "Uncategorized", "count": 1},
            ],
        )

    def test_student_cannot_access_dashboard(self):
        response = self.client.get("/dashboard", headers=self.student_headers)
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
