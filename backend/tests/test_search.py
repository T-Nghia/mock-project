import uuid
import unittest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.core.database import Base, get_db
from app.core.security import create_access_token
from app.models.user import User, UserRole
from app.models.folder import Folder
from app.models.document import Document
from app.models.tag import Tag, DocumentTag

# In-memory SQLite engine for unit tests
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class TestSearchAPI(unittest.TestCase):
    """Unit test suite for Search API endpoints using Python unittest framework."""

    def setUp(self):
        """Prepare fresh in-memory database schema, client, and seed data for each test."""
        Base.metadata.create_all(bind=engine)
        self.db = TestingSessionLocal()

        # Override get_db dependency to point to SQLite in-memory test database
        def _override_get_db():
            try:
                yield self.db
            finally:
                pass

        app.dependency_overrides[get_db] = _override_get_db
        self.client = TestClient(app)

        # 1. Seed test user & JWT token
        self.user = User(
            id=uuid.uuid4(),
            full_name="Test Student",
            email="student@example.com",
            hashed_password="hashed_pass",
            role=UserRole.STUDENT,
            is_active=True,
        )
        self.db.add(self.user)
        self.db.commit()
        self.db.refresh(self.user)

        self.token = create_access_token(subject=str(self.user.id), role=self.user.role.value)
        self.headers = {"Authorization": f"Bearer {self.token}"}

        # 2. Seed test folders
        self.folder_math = Folder(id=uuid.uuid4(), name="Toán Căn Bản", subject="Toán Hợp Phần 1", owner_id=self.user.id)
        self.folder_physics = Folder(id=uuid.uuid4(), name="Vật Lý Đại Cương", subject="Vật Lý", owner_id=self.user.id)
        self.db.add_all([self.folder_math, self.folder_physics])
        self.db.commit()

        # 3. Seed test documents
        self.doc1 = Document(
            id=uuid.uuid4(),
            title="Giáo trình Giải tích 1",
            file_path="/uploads/giai_tich_1.pdf",
            file_type="pdf",
            folder_id=self.folder_math.id,
            uploaded_by=self.user.id,
            summary="Tài liệu giáo trình giải tích hàm một biến",
        )
        self.doc2 = Document(
            id=uuid.uuid4(),
            title="Bài tập Đại số Tuyến tính",
            file_path="/uploads/dai_so.pdf",
            file_type="pdf",
            folder_id=self.folder_math.id,
            uploaded_by=self.user.id,
            summary="Tổng hợp bài tập đại số kèm lời giải",
        )
        self.doc3 = Document(
            id=uuid.uuid4(),
            title="Thí nghiệm Cơ học",
            file_path="/uploads/co_hoc.pdf",
            file_type="pdf",
            folder_id=self.folder_physics.id,
            uploaded_by=self.user.id,
            summary="Hướng dẫn thực hành cơ học cổ điển",
        )
        self.db.add_all([self.doc1, self.doc2, self.doc3])
        self.db.commit()

        # 4. Seed test tags
        self.tag_de_thi = Tag(id=uuid.uuid4(), name="Đề thi")
        self.tag_giao_trinh = Tag(id=uuid.uuid4(), name="Giáo trình")
        self.db.add_all([self.tag_de_thi, self.tag_giao_trinh])
        self.db.commit()

        # 5. Link document tags
        dt1 = DocumentTag(document_id=self.doc1.id, tag_id=self.tag_giao_trinh.id)
        dt2 = DocumentTag(document_id=self.doc2.id, tag_id=self.tag_de_thi.id)
        self.db.add_all([dt1, dt2])
        self.db.commit()

    def tearDown(self):
        """Clean up database session and drop all tables after each test."""
        self.db.close()
        Base.metadata.drop_all(bind=engine)
        app.dependency_overrides.clear()

    def test_unauthenticated_search(self):
        """Test search returns 401 Unauthorized if token is missing."""
        response = self.client.get("/api/v1/search")
        self.assertEqual(response.status_code, 401)

    def test_search_by_title(self):
        """Test Search by Title (query substring)."""
        response = self.client.get("/api/v1/search?title=Giải tích", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["items"][0]["title"], "Giáo trình Giải tích 1")

    def test_search_by_tag(self):
        """Test Search by Tag filter."""
        response = self.client.get("/api/v1/search?tags=Đề thi", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["items"][0]["title"], "Bài tập Đại số Tuyến tính")

    def test_search_by_subject(self):
        """Test Search by Subject filter."""
        response = self.client.get("/api/v1/search?subject=Toán Hợp Phần 1", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total"], 2)

    def test_combined_search(self):
        """Test combined search with Title, Subject, and Tag simultaneously."""
        response = self.client.get(
            "/api/v1/search?title=Giáo trình&subject=Toán Hợp Phần 1&tags=Giáo trình",
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["items"][0]["title"], "Giáo trình Giải tích 1")


if __name__ == "__main__":
    unittest.main()
