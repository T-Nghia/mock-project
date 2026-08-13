import os
import shutil
import tempfile
import unittest
import uuid

os.environ["DATABASE_URL"] = "sqlite://"

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.database import Base, get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models.document import Document
from app.models.social import Bookmark, Comment, Rating
from app.models.user import User, UserRole

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


class SocialAPITestCase(unittest.TestCase):
    """Kiểm thử module User Features: Bookmark, Comment, Rating."""

    def setUp(self):
        self.previous_db_override = app.dependency_overrides.get(get_db)
        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)

        self._tmp_upload_dir = tempfile.mkdtemp(prefix="slrms_test_uploads_")
        self._original_upload_dir = settings.UPLOAD_DIR
        settings.UPLOAD_DIR = self._tmp_upload_dir

        db = TestingSessionLocal()
        db.query(Bookmark).delete()
        db.query(Comment).delete()
        db.query(Rating).delete()
        db.query(Document).delete()
        db.query(User).delete()
        db.commit()
        db.close()

        self.teacher = self._create_user("teacher@example.com", UserRole.TEACHER)
        self.student_a = self._create_user("student-a@example.com", UserRole.STUDENT)
        self.student_b = self._create_user("student-b@example.com", UserRole.STUDENT)
        self.admin = self._create_user("admin@example.com", UserRole.ADMIN)

        self.teacher_headers = self._auth_headers(self.teacher)
        self.student_a_headers = self._auth_headers(self.student_a)
        self.student_b_headers = self._auth_headers(self.student_b)
        self.admin_headers = self._auth_headers(self.admin)

        self.document_id = self._upload_document()

    def tearDown(self):
        if self.previous_db_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = self.previous_db_override
        settings.UPLOAD_DIR = self._original_upload_dir
        shutil.rmtree(self._tmp_upload_dir, ignore_errors=True)

    # ---- helpers -----------------------------------------------------

    @staticmethod
    def _create_user(email: str, role: UserRole) -> User:
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

    @staticmethod
    def _auth_headers(user: User) -> dict[str, str]:
        token = create_access_token(subject=str(user.id), role=user.role.value)
        return {"Authorization": f"Bearer {token}"}

    def _upload_document(self, title: str = "Tai lieu mau") -> str:
        files = {"file": ("bai-giang.txt", b"Noi dung mau.", "text/plain")}
        response = self.client.post(
            "/documents/upload",
            headers=self.teacher_headers,
            files=files,
            data={"title": title},
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["id"]

    # ---- Bookmark --------------------------------------------------------

    def test_bookmark_add_status_and_list(self):
        response = self.client.post(
            f"/documents/{self.document_id}/bookmark", headers=self.student_a_headers
        )
        self.assertEqual(response.status_code, 201, response.text)
        self.assertTrue(response.json()["bookmarked"])

        status_resp = self.client.get(
            f"/documents/{self.document_id}/bookmark", headers=self.student_a_headers
        )
        self.assertEqual(status_resp.status_code, 200)
        self.assertTrue(status_resp.json()["bookmarked"])

        # Student khac chua bookmark thi phai la False.
        other_status = self.client.get(
            f"/documents/{self.document_id}/bookmark", headers=self.student_b_headers
        )
        self.assertFalse(other_status.json()["bookmarked"])

        my_list = self.client.get("/me/bookmarks", headers=self.student_a_headers)
        self.assertEqual(my_list.status_code, 200)
        body = my_list.json()
        self.assertEqual(body["total"], 1)
        self.assertEqual(body["items"][0]["id"], self.document_id)

    def test_bookmark_add_is_idempotent(self):
        for _ in range(3):
            response = self.client.post(
                f"/documents/{self.document_id}/bookmark", headers=self.student_a_headers
            )
            self.assertEqual(response.status_code, 201, response.text)

        my_list = self.client.get("/me/bookmarks", headers=self.student_a_headers)
        self.assertEqual(my_list.json()["total"], 1)

    def test_bookmark_remove_is_idempotent(self):
        self.client.post(
            f"/documents/{self.document_id}/bookmark", headers=self.student_a_headers
        )
        for _ in range(2):
            response = self.client.delete(
                f"/documents/{self.document_id}/bookmark", headers=self.student_a_headers
            )
            self.assertEqual(response.status_code, 200, response.text)
            self.assertFalse(response.json()["bookmarked"])

    def test_bookmark_nonexistent_document_returns_404(self):
        response = self.client.post(
            f"/documents/{uuid.uuid4()}/bookmark", headers=self.student_a_headers
        )
        self.assertEqual(response.status_code, 404, response.text)

    def test_bookmark_without_token_is_rejected(self):
        response = self.client.post(f"/documents/{self.document_id}/bookmark")
        self.assertEqual(response.status_code, 401, response.text)

    # ---- Comment -----------------------------------------------------------

    def test_add_and_list_comments_newest_first(self):
        first = self.client.post(
            f"/documents/{self.document_id}/comments",
            headers=self.student_a_headers,
            json={"content": "Binh luan dau tien"},
        )
        self.assertEqual(first.status_code, 201, first.text)
        self.assertEqual(first.json()["author_name"], self.student_a.full_name)

        second = self.client.post(
            f"/documents/{self.document_id}/comments",
            headers=self.teacher_headers,
            json={"content": "Binh luan thu hai"},
        )
        self.assertEqual(second.status_code, 201, second.text)

        listing = self.client.get(
            f"/documents/{self.document_id}/comments", headers=self.student_b_headers
        )
        self.assertEqual(listing.status_code, 200, listing.text)
        body = listing.json()
        self.assertEqual(body["total"], 2)
        # Moi nhat truoc.
        self.assertEqual(body["items"][0]["content"], "Binh luan thu hai")
        self.assertEqual(body["items"][1]["content"], "Binh luan dau tien")

    def test_comment_empty_content_is_rejected(self):
        response = self.client.post(
            f"/documents/{self.document_id}/comments",
            headers=self.student_a_headers,
            json={"content": ""},
        )
        self.assertEqual(response.status_code, 422, response.text)

    def test_comment_owner_can_delete_own_comment(self):
        created = self.client.post(
            f"/documents/{self.document_id}/comments",
            headers=self.student_a_headers,
            json={"content": "Se bi xoa"},
        ).json()

        response = self.client.delete(
            f"/comments/{created['id']}", headers=self.student_a_headers
        )
        self.assertEqual(response.status_code, 204, response.text)

        listing = self.client.get(
            f"/documents/{self.document_id}/comments", headers=self.student_a_headers
        )
        self.assertEqual(listing.json()["total"], 0)

    def test_other_student_cannot_delete_comment(self):
        created = self.client.post(
            f"/documents/{self.document_id}/comments",
            headers=self.student_a_headers,
            json={"content": "Cua student A"},
        ).json()

        response = self.client.delete(
            f"/comments/{created['id']}", headers=self.student_b_headers
        )
        self.assertEqual(response.status_code, 403, response.text)

    def test_admin_can_delete_any_comment(self):
        created = self.client.post(
            f"/documents/{self.document_id}/comments",
            headers=self.student_a_headers,
            json={"content": "Cua student A"},
        ).json()

        response = self.client.delete(
            f"/comments/{created['id']}", headers=self.admin_headers
        )
        self.assertEqual(response.status_code, 204, response.text)

    def test_delete_nonexistent_comment_returns_404(self):
        response = self.client.delete(
            f"/comments/{uuid.uuid4()}", headers=self.teacher_headers
        )
        self.assertEqual(response.status_code, 404, response.text)

    # ---- Rating -------------------------------------------------------------

    def test_rating_upsert_and_average(self):
        r1 = self.client.put(
            f"/documents/{self.document_id}/rating",
            headers=self.student_a_headers,
            json={"score": 4},
        )
        self.assertEqual(r1.status_code, 200, r1.text)
        self.assertEqual(r1.json()["average"], 4)
        self.assertEqual(r1.json()["count"], 1)
        self.assertEqual(r1.json()["my_score"], 4)

        r2 = self.client.put(
            f"/documents/{self.document_id}/rating",
            headers=self.student_b_headers,
            json={"score": 2},
        )
        self.assertEqual(r2.status_code, 200, r2.text)
        self.assertEqual(r2.json()["average"], 3)
        self.assertEqual(r2.json()["count"], 2)

    def test_rating_upsert_replaces_previous_score_from_same_user(self):
        self.client.put(
            f"/documents/{self.document_id}/rating",
            headers=self.student_a_headers,
            json={"score": 5},
        )
        response = self.client.put(
            f"/documents/{self.document_id}/rating",
            headers=self.student_a_headers,
            json={"score": 1},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["average"], 1)
        self.assertEqual(response.json()["count"], 1)

    def test_rating_out_of_range_is_rejected(self):
        response = self.client.put(
            f"/documents/{self.document_id}/rating",
            headers=self.student_a_headers,
            json={"score": 6},
        )
        self.assertEqual(response.status_code, 422, response.text)

    def test_rating_remove(self):
        self.client.put(
            f"/documents/{self.document_id}/rating",
            headers=self.student_a_headers,
            json={"score": 3},
        )
        response = self.client.delete(
            f"/documents/{self.document_id}/rating", headers=self.student_a_headers
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIsNone(response.json()["average"])
        self.assertEqual(response.json()["count"], 0)
        self.assertIsNone(response.json()["my_score"])

    def test_rating_summary_when_nobody_rated_yet(self):
        response = self.client.get(
            f"/documents/{self.document_id}/rating", headers=self.student_a_headers
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertIsNone(body["average"])
        self.assertEqual(body["count"], 0)
        self.assertIsNone(body["my_score"])


if __name__ == "__main__":
    unittest.main()
