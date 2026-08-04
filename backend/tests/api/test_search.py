import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.core.database import Base, get_db
from app.core.security import create_access_token
from app.models.user import User, UserRole
from app.models.folder import Folder
from app.models.document import Document
from app.models.tag import Tag, DocumentTag

# In-memory SQLite engine for unit tests
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db_session():
    """Create a fresh database schema for each test."""
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db_session):
    """Override get_db dependency with test database session."""
    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def test_user(db_session) -> tuple[User, str]:
    """Create a test user and generate JWT token."""
    user = User(
        id=uuid.uuid4(),
        full_name="Test Student",
        email="student@example.com",
        hashed_password="hashed_pass",
        role=UserRole.STUDENT,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    token = create_access_token(subject=str(user.id), role=user.role.value)
    return user, token


@pytest.fixture(scope="function")
def sample_data(db_session, test_user):
    """Seed test data for folders, documents, and tags."""
    user, _ = test_user

    # Folders
    folder_math = Folder(id=uuid.uuid4(), name="Toán Căn Bản", subject="Toán Hợp Phần 1", owner_id=user.id)
    folder_physics = Folder(id=uuid.uuid4(), name="Vật Lý Đại Cương", subject="Vật Lý", owner_id=user.id)
    db_session.add_all([folder_math, folder_physics])
    db_session.commit()

    # Documents
    doc1 = Document(
        id=uuid.uuid4(),
        title="Giáo trình Giải tích 1",
        file_path="/uploads/giai_tich_1.pdf",
        file_type="pdf",
        folder_id=folder_math.id,
        uploaded_by=user.id,
        summary="Tài liệu giáo trình giải tích hàm một biến",
    )
    doc2 = Document(
        id=uuid.uuid4(),
        title="Bài tập Đại số Tuyến tính",
        file_path="/uploads/dai_so.pdf",
        file_type="pdf",
        folder_id=folder_math.id,
        uploaded_by=user.id,
        summary="Tổng hợp bài tập đại số kèm lời giải",
    )
    doc3 = Document(
        id=uuid.uuid4(),
        title="Thí nghiệm Cơ học",
        file_path="/uploads/co_hoc.pdf",
        file_type="pdf",
        folder_id=folder_physics.id,
        uploaded_by=user.id,
        summary="Hướng dẫn thực hành cơ học cổ điển",
    )
    db_session.add_all([doc1, doc2, doc3])
    db_session.commit()

    # Tags
    tag_de_thi = Tag(id=uuid.uuid4(), name="Đề thi")
    tag_giao_trinh = Tag(id=uuid.uuid4(), name="Giáo trình")
    db_session.add_all([tag_de_thi, tag_giao_trinh])
    db_session.commit()

    # Document Tags
    dt1 = DocumentTag(document_id=doc1.id, tag_id=tag_giao_trinh.id)
    dt2 = DocumentTag(document_id=doc2.id, tag_id=tag_de_thi.id)
    db_session.add_all([dt1, dt2])
    db_session.commit()

    return {
        "user": user,
        "folder_math": folder_math,
        "doc1": doc1,
        "doc2": doc2,
        "doc3": doc3,
        "tag_de_thi": tag_de_thi,
        "tag_giao_trinh": tag_giao_trinh,
    }


def test_unauthenticated_search(client):
    """Ensure search returns 401 Unauthorized if token is missing."""
    response = client.get("/api/v1/search")
    assert response.status_code == 401


def test_search_by_name(client, test_user, sample_data):
    """Test Search by Name (query substring)."""
    _, token = test_user
    headers = {"Authorization": f"Bearer {token}"}

    response = client.get("/api/v1/search?q=Giải tích", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "Giáo trình Giải tích 1"


def test_search_by_tag(client, test_user, sample_data):
    """Test Search by Tag filter."""
    _, token = test_user
    headers = {"Authorization": f"Bearer {token}"}

    response = client.get("/api/v1/search?tags=Đề thi", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "Bài tập Đại số Tuyến tính"


def test_search_by_subject(client, test_user, sample_data):
    """Test Search by Subject filter."""
    _, token = test_user
    headers = {"Authorization": f"Bearer {token}"}

    response = client.get("/api/v1/search?subject=Toán Hợp Phần 1", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2


def test_combined_search(client, test_user, sample_data):
    """Test combined search with Name, Subject, and Tag simultaneously."""
    _, token = test_user
    headers = {"Authorization": f"Bearer {token}"}

    response = client.get(
        "/api/v1/search?q=Giáo trình&subject=Toán Hợp Phần 1&tags=Giáo trình",
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "Giáo trình Giải tích 1"
