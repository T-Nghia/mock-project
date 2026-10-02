import os
import unittest
import uuid

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


class FolderAPITestCase(unittest.TestCase):
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

        self.teacher = self.create_user("teacher@example.com", UserRole.TEACHER)
        self.other_teacher = self.create_user("other@example.com", UserRole.TEACHER)
        self.student = self.create_user("student@example.com", UserRole.STUDENT)
        self.teacher_headers = self.login_headers("teacher@example.com")
        self.other_headers = self.login_headers("other@example.com")
        self.student_headers = self.login_headers("student@example.com")

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

    def create_folder(self, payload: dict, headers=None) -> dict:
        response = self.client.post(
            "/folders",
            json=payload,
            headers=headers or self.teacher_headers,
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_only_teacher_can_manage_folders_and_tree_is_nested(self):
        forbidden = self.client.post(
            "/folders",
            json={"name": "Python", "subject": "Python"},
            headers=self.student_headers,
        )
        self.assertEqual(forbidden.status_code, 403)

        root = self.create_folder({"name": "Python", "subject": "Python"})
        chapter = self.create_folder(
            {"name": "Chuong 1", "parent_folder_id": root["id"]}
        )
        topic = self.create_folder(
            {"name": "Bien va kieu du lieu", "parent_folder_id": chapter["id"]}
        )

        tree_response = self.client.get("/folders/tree", headers=self.teacher_headers)
        self.assertEqual(tree_response.status_code, 200, tree_response.text)
        tree = tree_response.json()
        self.assertEqual(len(tree), 1)
        self.assertEqual(tree[0]["id"], root["id"])
        self.assertEqual(tree[0]["children"][0]["id"], chapter["id"])
        self.assertEqual(
            tree[0]["children"][0]["children"][0]["id"], topic["id"]
        )
        self.assertEqual(topic["subject"], "Python")

    def test_duplicate_name_is_blocked_only_among_siblings(self):
        root_a = self.create_folder({"name": "Python"})
        root_b = self.create_folder({"name": "Java"})
        self.create_folder({"name": "Chuong 1", "parent_folder_id": root_a["id"]})

        duplicate = self.client.post(
            "/folders",
            json={"name": "  chuong 1  ", "parent_folder_id": root_a["id"]},
            headers=self.teacher_headers,
        )
        self.assertEqual(duplicate.status_code, 409)

        allowed = self.client.post(
            "/folders",
            json={"name": "Chuong 1", "parent_folder_id": root_b["id"]},
            headers=self.teacher_headers,
        )
        self.assertEqual(allowed.status_code, 201, allowed.text)

    def test_move_folder_propagates_subject_and_prevents_cycles(self):
        python = self.create_folder({"name": "Python"})
        java = self.create_folder({"name": "Java"})
        chapter = self.create_folder(
            {"name": "Chuong", "parent_folder_id": python["id"]}
        )
        topic = self.create_folder(
            {"name": "Chu de", "parent_folder_id": chapter["id"]}
        )

        cycle = self.client.patch(
            f"/folders/{chapter['id']}",
            json={"parent_folder_id": topic["id"]},
            headers=self.teacher_headers,
        )
        self.assertEqual(cycle.status_code, 400)

        moved = self.client.patch(
            f"/folders/{chapter['id']}",
            json={"parent_folder_id": java["id"]},
            headers=self.teacher_headers,
        )
        self.assertEqual(moved.status_code, 200, moved.text)
        self.assertEqual(moved.json()["subject"], "Java")

        topic_response = self.client.get(
            f"/folders/{topic['id']}", headers=self.teacher_headers
        )
        self.assertEqual(topic_response.json()["subject"], "Java")

    def test_move_document_list_recursive_and_safe_recursive_delete(self):
        root = self.create_folder({"name": "Python"})
        chapter = self.create_folder(
            {"name": "Chuong 1", "parent_folder_id": root["id"]}
        )

        db = TestingSessionLocal()
        document = Document(
            title="Tai lieu bien",
            file_path="uploads/variables.pdf",
            file_type="pdf",
            folder_id=uuid.UUID(chapter["id"]),
            uploaded_by=self.teacher.id,
            processing_status=ProcessingStatus.PENDING,
        )
        db.add(document)
        db.commit()
        db.refresh(document)
        document_id = document.id
        db.close()

        recursive_list = self.client.get(
            f"/folders/{root['id']}/documents?recursive=true",
            headers=self.teacher_headers,
        )
        self.assertEqual(recursive_list.status_code, 200, recursive_list.text)
        self.assertEqual([item["id"] for item in recursive_list.json()], [str(document_id)])

        unfiled = self.client.patch(
            f"/folders/documents/{document_id}",
            json={"folder_id": None},
            headers=self.teacher_headers,
        )
        self.assertEqual(unfiled.status_code, 200, unfiled.text)
        self.assertIsNone(unfiled.json()["folder_id"])

        moved_back = self.client.patch(
            f"/folders/documents/{document_id}",
            json={"folder_id": chapter["id"]},
            headers=self.teacher_headers,
        )
        self.assertEqual(moved_back.status_code, 200, moved_back.text)

        deleted = self.client.delete(
            f"/folders/{root['id']}", headers=self.teacher_headers
        )
        self.assertEqual(deleted.status_code, 204, deleted.text)

        db = TestingSessionLocal()
        self.assertEqual(db.query(Folder).count(), 0)
        kept_document = db.query(Document).filter(Document.id == document_id).one()
        self.assertIsNone(kept_document.folder_id)
        db.close()

    def test_teacher_cannot_use_another_teachers_folder(self):
        private_folder = self.create_folder({"name": "Private"})

        hidden = self.client.get(
            f"/folders/{private_folder['id']}", headers=self.other_headers
        )
        self.assertEqual(hidden.status_code, 404)

        create_under_private = self.client.post(
            "/folders",
            json={"name": "Child", "parent_folder_id": private_folder["id"]},
            headers=self.other_headers,
        )
        self.assertEqual(create_under_private.status_code, 404)


if __name__ == "__main__":
    unittest.main()
