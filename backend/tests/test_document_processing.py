import tempfile
import unittest
import uuid
from pathlib import Path

from app.models.document import Document, DocumentChunk, ProcessingStatus
from app.services.document_service import DocumentService
from app.utils.text_extract import EMBEDDING_DIM


class FakeDocumentRepository:
    def __init__(self, document: Document):
        self.document = document
        self.chunks: list[DocumentChunk] = []
        self.statuses: list[ProcessingStatus] = []

    def get_by_id(self, document_id):
        if self.document.id == document_id:
            return self.document
        return None

    def update_status(self, document, status, summary=None):
        document.processing_status = status
        if summary is not None:
            document.summary = summary
        self.statuses.append(status)
        return document

    def add_chunks(self, chunks):
        self.chunks.extend(chunks)


class DocumentProcessingTestCase(unittest.TestCase):
    def create_document_with_content(self, content: str) -> tuple[Document, tempfile.TemporaryDirectory]:
        temp_dir = tempfile.TemporaryDirectory()
        file_path = Path(temp_dir.name) / "document.txt"
        file_path.write_text(content, encoding="utf-8")
        document = Document(
            id=uuid.uuid4(),
            title="Tai lieu test",
            file_path=str(file_path),
            file_type="txt",
            uploaded_by=uuid.uuid4(),
            processing_status=ProcessingStatus.PENDING,
        )
        return document, temp_dir

    def test_empty_document_is_marked_failed_instead_of_done(self):
        document, temp_dir = self.create_document_with_content("   ")
        self.addCleanup(temp_dir.cleanup)
        repo = FakeDocumentRepository(document)
        service = DocumentService(repo, tag_repo=None)

        with self.assertRaises(ValueError):
            service.process_document_sync(document.id)

        self.assertEqual(document.processing_status, ProcessingStatus.FAILED)
        self.assertEqual(repo.statuses, [ProcessingStatus.PROCESSING, ProcessingStatus.FAILED])
        self.assertEqual(repo.chunks, [])

    def test_text_document_with_content_becomes_done_with_embedded_chunks(self):
        document, temp_dir = self.create_document_with_content(
            "FastAPI la framework Python dung de xay dung API. "
            "Uvicorn la ASGI server thuong dung de chay FastAPI."
        )
        self.addCleanup(temp_dir.cleanup)
        repo = FakeDocumentRepository(document)
        service = DocumentService(repo, tag_repo=None)

        service.process_document_sync(document.id)

        self.assertEqual(document.processing_status, ProcessingStatus.DONE)
        self.assertIn(ProcessingStatus.PROCESSING, repo.statuses)
        self.assertIn(ProcessingStatus.DONE, repo.statuses)
        self.assertGreater(len(repo.chunks), 0)
        self.assertTrue(all(chunk.embedding is not None for chunk in repo.chunks))
        self.assertTrue(all(len(chunk.embedding) == EMBEDDING_DIM for chunk in repo.chunks))


if __name__ == "__main__":
    unittest.main()
