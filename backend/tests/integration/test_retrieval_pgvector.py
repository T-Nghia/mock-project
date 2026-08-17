import unittest
import uuid

from sqlalchemy.orm import Session

from app.core.database import engine
from app.models.document import EMBEDDING_DIM, Document, DocumentChunk, ProcessingStatus
from app.models.folder import Folder  # noqa: F401 - register folders table for Document FK
from app.models.user import User, UserRole
from app.repositories.retrieval_repo import RetrievalRepository


def basis_vector(index: int) -> list[float]:
    vector = [0.0] * EMBEDDING_DIM
    vector[index] = 1.0
    return vector


class RetrievalPgvectorTestCase(unittest.TestCase):
    def setUp(self):
        self.connection = engine.connect()
        self.transaction = self.connection.begin()
        self.db = Session(bind=self.connection)
        self.user = self._create_user()

    def tearDown(self):
        self.db.close()
        self.transaction.rollback()
        self.connection.close()

    def _create_user(self) -> User:
        user = User(
            full_name="Teacher Test",
            email=f"teacher-{uuid.uuid4()}@example.com",
            hashed_password="hashed",
            role=UserRole.TEACHER,
            is_active=True,
        )
        self.db.add(user)
        self.db.flush()
        return user

    def _create_document(self, status=ProcessingStatus.DONE) -> Document:
        document = Document(
            title="Tai lieu retrieval",
            file_path=f"/tmp/{uuid.uuid4()}.txt",
            file_type="txt",
            uploaded_by=self.user.id,
            processing_status=status,
        )
        self.db.add(document)
        self.db.flush()
        return document

    def _create_chunk(self, document: Document, index: int, content: str, embedding):
        chunk = DocumentChunk(
            document_id=document.id,
            chunk_index=index,
            content=content,
            embedding=embedding,
        )
        self.db.add(chunk)
        self.db.flush()
        return chunk

    def test_database_is_postgresql_with_vector_extension(self):
        self.assertEqual(engine.dialect.name, "postgresql")
        installed = self.connection.exec_driver_sql(
            "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')"
        ).scalar_one()
        self.assertTrue(installed)

    def test_retrieve_chunks_does_not_leak_other_documents(self):
        document_a = self._create_document()
        document_b = self._create_document()
        chunk_a = self._create_chunk(document_a, 0, "Noi dung tai lieu A", basis_vector(0))
        chunk_b = self._create_chunk(document_b, 0, "Noi dung tai lieu B", basis_vector(1))
        repository = RetrievalRepository(self.db)

        results = repository.retrieve_chunks(
            document_id=document_a.id,
            query_embedding=basis_vector(1),
            top_k=5,
        )

        self.assertEqual([item.chunk_id for item in results], [chunk_a.id])
        self.assertTrue(all(item.document_id == document_a.id for item in results))
        self.assertNotIn(chunk_b.id, {item.chunk_id for item in results})

    def test_retrieve_chunks_orders_by_relevance_and_limits_top_k(self):
        document = self._create_document()
        closest = self._create_chunk(document, 0, "Gan cau hoi nhat", basis_vector(2))
        self._create_chunk(document, 1, "Kem lien quan hon", basis_vector(1))
        second = self._create_chunk(
            document,
            2,
            "Gan thu hai",
            [0.0, 0.6, 0.8] + [0.0] * (EMBEDDING_DIM - 3),
        )
        repository = RetrievalRepository(self.db)

        results = repository.retrieve_chunks(
            document_id=document.id,
            query_embedding=basis_vector(2),
            top_k=2,
        )

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].chunk_id, closest.id)
        self.assertEqual(results[1].chunk_id, second.id)
        self.assertGreaterEqual(results[0].score, results[1].score)

    def test_retrieve_chunks_ignores_not_ready_documents_and_null_embeddings(self):
        pending_document = self._create_document(ProcessingStatus.PENDING)
        failed_document = self._create_document(ProcessingStatus.FAILED)
        done_document = self._create_document(ProcessingStatus.DONE)
        self._create_chunk(pending_document, 0, "Dang xu ly", basis_vector(0))
        self._create_chunk(failed_document, 0, "Xu ly loi", basis_vector(0))
        self._create_chunk(done_document, 0, "Khong co embedding", None)
        repository = RetrievalRepository(self.db)

        self.assertEqual(
            repository.retrieve_chunks(
                document_id=pending_document.id,
                query_embedding=basis_vector(0),
                top_k=5,
            ),
            [],
        )
        self.assertEqual(
            repository.retrieve_chunks(
                document_id=failed_document.id,
                query_embedding=basis_vector(0),
                top_k=5,
            ),
            [],
        )
        self.assertEqual(
            repository.retrieve_chunks(
                document_id=done_document.id,
                query_embedding=basis_vector(0),
                top_k=5,
            ),
            [],
        )


if __name__ == "__main__":
    unittest.main()
