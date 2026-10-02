import os
import shutil
import tempfile
import unittest
import uuid
from pathlib import Path

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
from app.models.folder import Folder
from app.models.tag import DocumentTag, Tag
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


class DocumentAPITestCase(unittest.TestCase):
    """Kiểm thử module Document: Upload, View Metadata, Download (mục 2.2)."""

    def setUp(self):
        self.previous_db_override = app.dependency_overrides.get(get_db)
        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)

        # Sandbox UPLOAD_DIR vào thư mục tạm cho từng test, tránh phụ thuộc
        # vào đường dẫn "/app/uploads" mặc định (chỉ tồn tại trong container)
        # và tránh để rác lại trên máy chạy test.
        self._tmp_upload_dir = tempfile.mkdtemp(prefix="slrms_test_uploads_")
        self._original_upload_dir = settings.UPLOAD_DIR
        settings.UPLOAD_DIR = self._tmp_upload_dir

        db = TestingSessionLocal()
        db.query(DocumentTag).delete()
        db.query(Document).delete()
        db.query(Tag).delete()
        db.query(Folder).delete()
        db.query(User).delete()
        db.commit()
        db.close()

        self.teacher = self._create_user("teacher@example.com", UserRole.TEACHER)
        self.student = self._create_user("student@example.com", UserRole.STUDENT)
        self.teacher_headers = self._auth_headers(self.teacher)
        self.student_headers = self._auth_headers(self.student)

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

    def _upload(
        self,
        headers: dict[str, str],
        filename: str = "bai-giang.txt",
        content: bytes = b"Noi dung tai lieu mau.",
        **form,
    ):
        files = {"file": (filename, content, "text/plain")}
        return self.client.post(
            "/documents/upload", headers=headers, files=files, data=form
        )

    def _uploaded_file_path(self) -> Path:
        saved = list(Path(self._tmp_upload_dir).glob("*"))
        self.assertEqual(len(saved), 1, "Expected exactly one file in the upload dir")
        return saved[0]

    # ---- Upload --------------------------------------------------------

    def test_upload_success_persists_file_and_hides_internal_path(self):
        response = self._upload(
            self.teacher_headers,
            filename="chuong-1.txt",
            content=b"Noi dung chuong 1.",
            title="Chuong 1 - Bien",
            tags="python, co-ban",
        )
        self.assertEqual(response.status_code, 201, response.text)
        body = response.json()

        self.assertEqual(body["title"], "Chuong 1 - Bien")
        self.assertEqual(body["file_type"], "txt")
        self.assertEqual(body["processing_status"], "pending")
        self.assertEqual(body["uploaded_by"], str(self.teacher.id))
        # Không được lộ đường dẫn tuyệt đối trên server ra response.
        self.assertNotIn("file_path", body)

        saved_file = self._uploaded_file_path()
        self.assertEqual(saved_file.read_bytes(), b"Noi dung chuong 1.")

    def test_student_cannot_upload_document(self):
        response = self._upload(self.student_headers)
        self.assertEqual(response.status_code, 403, response.text)

    def test_upload_without_token_is_rejected(self):
        response = self._upload(headers={})
        self.assertEqual(response.status_code, 401, response.text)

    def test_upload_rejects_disallowed_extension(self):
        response = self._upload(
            self.teacher_headers, filename="virus.exe", content=b"MZ"
        )
        self.assertEqual(response.status_code, 400, response.text)

    def test_upload_without_title_falls_back_to_filename(self):
        response = self._upload(self.teacher_headers, filename="ghi-chu.txt")
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["title"], "ghi-chu.txt")

    # ---- View Metadata (muc 2.2) ---------------------------------------

    def test_get_metadata_returns_full_details_and_matches_file_size(self):
        content = b"Noi dung day du de kiem tra dung luong file."
        upload = self._upload(
            self.teacher_headers, content=content, title="Tai lieu Test", tags="toan, dai-so"
        )
        document_id = upload.json()["id"]

        # Student cung co quyen xem metadata (READ_DOCUMENT).
        response = self.client.get(
            f"/documents/{document_id}", headers=self.student_headers
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()

        self.assertEqual(body["title"], "Tai lieu Test")
        self.assertEqual(body["file_size"], len(content))
        self.assertEqual(body["uploaded_by"]["full_name"], self.teacher.full_name)
        self.assertEqual(sorted(body["tags"]), ["dai-so", "toan"])
        self.assertNotIn("file_path", body)

    def test_get_metadata_not_found(self):
        response = self.client.get(
            f"/documents/{uuid.uuid4()}", headers=self.teacher_headers
        )
        self.assertEqual(response.status_code, 404, response.text)

    def test_get_metadata_without_token_is_rejected(self):
        upload = self._upload(self.teacher_headers)
        document_id = upload.json()["id"]
        response = self.client.get(f"/documents/{document_id}")
        self.assertEqual(response.status_code, 401, response.text)

    def test_get_metadata_when_file_missing_on_disk_still_returns_metadata(self):
        upload = self._upload(self.teacher_headers, title="Se bi xoa file")
        document_id = upload.json()["id"]
        self._uploaded_file_path().unlink()

        response = self.client.get(
            f"/documents/{document_id}", headers=self.teacher_headers
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIsNone(response.json()["file_size"])

    # ---- Download (muc 2.2) --------------------------------------------

    def test_download_returns_file_content_with_friendly_name(self):
        content = b"Noi dung file de download."
        upload = self._upload(
            self.teacher_headers,
            filename="raw-uuid-name.txt",
            content=content,
            title="Bai Giang Chuong 2",
        )
        document_id = upload.json()["id"]

        # Student cung tai duoc (READ_DOCUMENT).
        response = self.client.get(
            f"/documents/{document_id}/download", headers=self.student_headers
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.content, content)
        content_disposition = response.headers["content-disposition"]
        self.assertIn("attachment", content_disposition)
        # Starlette ma hoa filename co khoang trang theo RFC 5987 (filename*=utf-8''...)
        self.assertIn("Bai%20Giang%20Chuong%202.txt", content_disposition)

    def test_download_not_found(self):
        response = self.client.get(
            f"/documents/{uuid.uuid4()}/download", headers=self.teacher_headers
        )
        self.assertEqual(response.status_code, 404, response.text)

    def test_download_without_token_is_rejected(self):
        upload = self._upload(self.teacher_headers)
        document_id = upload.json()["id"]
        response = self.client.get(f"/documents/{document_id}/download")
        self.assertEqual(response.status_code, 401, response.text)

    def test_download_missing_file_on_disk_returns_404(self):
        upload = self._upload(self.teacher_headers, title="File se bi mat")
        document_id = upload.json()["id"]
        self._uploaded_file_path().unlink()

        response = self.client.get(
            f"/documents/{document_id}/download", headers=self.teacher_headers
        )
        self.assertEqual(response.status_code, 404, response.text)


if __name__ == "__main__":
    unittest.main()
