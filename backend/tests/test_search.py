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

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class TestSearchAPI(unittest.TestCase):

    def setUp(self):
        Base.metadata.create_all(bind=engine)
        self.db = TestingSessionLocal()

        def _override_get_db():
            try:
                yield self.db
            finally:
                pass

        app.dependency_overrides[get_db] = _override_get_db
        self.client = TestClient(app)

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

        self.folder_math = Folder(id=uuid.uuid4(), name="Toán Căn Bản", subject="Toán Hợp Phần 1", owner_id=self.user.id)
        self.folder_physics = Folder(id=uuid.uuid4(), name="Vật Lý Đại Cương", subject="Vật Lý", owner_id=self.user.id)
        self.folder_chemistry = Folder(id=uuid.uuid4(), name="Hóa Học Chuyên Ngành", subject="Hóa Học", owner_id=self.user.id)
        self.db.add_all([self.folder_math, self.folder_physics, self.folder_chemistry])
        self.db.commit()

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
        self.doc4 = Document(
            id=uuid.uuid4(),
            title="Hóa học Hữu cơ Nâng cao",
            file_path="/uploads/hoa_huu_co.pdf",
            file_type="pdf",
            folder_id=self.folder_chemistry.id,
            uploaded_by=self.user.id,
            summary="Tài liệu hóa học phản ứng hữu cơ",
        )
        self.doc5 = Document(
            id=uuid.uuid4(),
            title="Đề thi Toán cao cấp",
            file_path="/uploads/de_thi_toan.pdf",
            file_type="pdf",
            folder_id=self.folder_math.id,
            uploaded_by=self.user.id,
            summary="Bộ đề thi thử môn toán cao cấp có đáp án",
        )
        self.db.add_all([self.doc1, self.doc2, self.doc3, self.doc4, self.doc5])
        self.db.commit()

        self.tag_de_thi = Tag(id=uuid.uuid4(), name="Đề thi")
        self.tag_giao_trinh = Tag(id=uuid.uuid4(), name="Giáo trình")
        self.tag_toan = Tag(id=uuid.uuid4(), name="Toán")
        self.tag_thi_nghiem = Tag(id=uuid.uuid4(), name="Thí nghiệm")
        self.db.add_all([self.tag_de_thi, self.tag_giao_trinh, self.tag_toan, self.tag_thi_nghiem])
        self.db.commit()

        dt1 = DocumentTag(document_id=self.doc1.id, tag_id=self.tag_giao_trinh.id)
        dt2 = DocumentTag(document_id=self.doc1.id, tag_id=self.tag_toan.id)
        dt3 = DocumentTag(document_id=self.doc2.id, tag_id=self.tag_de_thi.id)
        dt4 = DocumentTag(document_id=self.doc3.id, tag_id=self.tag_thi_nghiem.id)
        dt5 = DocumentTag(document_id=self.doc5.id, tag_id=self.tag_de_thi.id)
        self.db.add_all([dt1, dt2, dt3, dt4, dt5])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=engine)
        app.dependency_overrides.clear()

    def test_unauthenticated_search(self):
        response = self.client.get("/search")
        self.assertEqual(response.status_code, 401)

    def test_keyword_search_matches_title(self):
        response = self.client.get("/search?keyword=Giải tích", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["items"][0]["title"], "Giáo trình Giải tích 1")

    def test_keyword_search_matches_tag(self):
        response = self.client.get("/search?keyword=Thí nghiệm", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["items"][0]["title"], "Thí nghiệm Cơ học")

    def test_keyword_search_matches_subject(self):
        response = self.client.get("/search?keyword=Hóa Học", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["items"][0]["title"], "Hóa học Hữu cơ Nâng cao")

    def test_keyword_search_matches_multiple_or(self):
        response = self.client.get("/search?keyword=Toán", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total"], 3)

    def test_keyword_search_no_match(self):
        response = self.client.get("/search?keyword=Triết học", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total"], 0)
        self.assertEqual(len(data["items"]), 0)

    def test_keyword_search_whitespace(self):
        response = self.client.get("/search?keyword=%20%20Giải%20tích%20%20", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total"], 1)


if __name__ == "__main__":
    unittest.main()
