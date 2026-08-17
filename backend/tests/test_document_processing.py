import tempfile
import unittest
import uuid
from pathlib import Path

from app.models.document import Document, DocumentChunk, ProcessingStatus
from app.core.config import settings
from app.services.document_service import DocumentService
from app.services.gemini_embedding_provider import GeminiEmbeddingProviderError
from app.utils.text_extract import EMBEDDING_DIM


class FakeDocumentRepository:
    def __init__(self, document: Document):
        self.document = document
        self.chunks: list[DocumentChunk] = []
        self.statuses: list[ProcessingStatus] = []
        self.chunk_batches = []

    def get_by_id(self, document_id):
        if self.document.id == document_id:
            return self.document
        return None

    def update_status(self, document, status, summary=None, suggested_questions=None):
        document.processing_status = status
        if summary is not None:
            document.summary = summary
        if suggested_questions is not None:
            document.suggested_questions = suggested_questions
        self.statuses.append(status)
        return document

    def add_chunks(self, chunks):
        self.chunk_batches.append(chunks)
        self.chunks.extend(chunks)


class FakeEmbeddingProvider:
    def __init__(self, failures=None):
        self.calls = []
        self.failures = list(failures or [])

    def embed_batch(self, texts, *, task_type):
        self.calls.append((list(texts), task_type))
        if self.failures:
            failure = self.failures.pop(0)
            if failure:
                raise failure
        return [[float(index)] * EMBEDDING_DIM for index, _ in enumerate(texts)]


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
        service = DocumentService(repo, tag_repo=None, embedding_provider=FakeEmbeddingProvider())

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
        service = DocumentService(repo, tag_repo=None, embedding_provider=FakeEmbeddingProvider())

        service.process_document_sync(document.id)

        self.assertEqual(document.processing_status, ProcessingStatus.DONE)
        self.assertIn(ProcessingStatus.PROCESSING, repo.statuses)
        self.assertIn(ProcessingStatus.DONE, repo.statuses)
        self.assertGreater(len(repo.chunks), 0)
        self.assertTrue(all(chunk.embedding is not None for chunk in repo.chunks))
        self.assertTrue(all(len(chunk.embedding) == EMBEDDING_DIM for chunk in repo.chunks))
        self.assertEqual(len(repo.chunk_batches), 1)

    def test_retryable_batch_failure_retries_before_persisting(self):
        document, temp_dir = self.create_document_with_content("Mot noi dung du dai de tao embedding.")
        self.addCleanup(temp_dir.cleanup)
        repo = FakeDocumentRepository(document)
        provider = FakeEmbeddingProvider(
            failures=[GeminiEmbeddingProviderError("temporary", retryable=True), None]
        )
        sleeps = []

        DocumentService(
            repo,
            tag_repo=None,
            embedding_provider=provider,
            sleep=sleeps.append,
        ).process_document_sync(document.id)

        self.assertEqual(len(provider.calls), 2)
        self.assertEqual(sleeps, [2])
        self.assertEqual(len(repo.chunk_batches), 1)

    def test_waits_between_successful_embedding_batches_but_not_after_last(self):
        document, temp_dir = self.create_document_with_content(
            "one two three four five six seven eight nine ten eleven twelve"
        )
        self.addCleanup(temp_dir.cleanup)
        repo = FakeDocumentRepository(document)
        provider = FakeEmbeddingProvider()
        sleeps = []
        original_chunk_tokens = settings.GEMINI_EMBEDDING_CHUNK_TOKENS
        original_overlap_tokens = settings.GEMINI_EMBEDDING_CHUNK_OVERLAP_TOKENS
        original_batch_tokens = settings.GEMINI_EMBEDDING_BATCH_TOKENS
        settings.GEMINI_EMBEDDING_CHUNK_TOKENS = 3
        settings.GEMINI_EMBEDDING_CHUNK_OVERLAP_TOKENS = 1
        settings.GEMINI_EMBEDDING_BATCH_TOKENS = 6
        self.addCleanup(
            setattr,
            settings,
            "GEMINI_EMBEDDING_CHUNK_TOKENS",
            original_chunk_tokens,
        )
        self.addCleanup(
            setattr,
            settings,
            "GEMINI_EMBEDDING_CHUNK_OVERLAP_TOKENS",
            original_overlap_tokens,
        )
        self.addCleanup(
            setattr,
            settings,
            "GEMINI_EMBEDDING_BATCH_TOKENS",
            original_batch_tokens,
        )

        DocumentService(
            repo,
            tag_repo=None,
            embedding_provider=provider,
            sleep=sleeps.append,
        ).process_document_sync(document.id)

        self.assertEqual(len(provider.calls), 3)
        self.assertEqual(sleeps, [60, 60])
        self.assertEqual(len(repo.chunk_batches), 3)


if __name__ == "__main__":
    unittest.main()
