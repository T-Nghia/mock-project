import unittest
import uuid

from app.models.document import EMBEDDING_DIM
from app.schemas.retrieval import RetrievedChunk
from app.services.retrieval_service import RetrievalService


class FakeRetrievalRepository:
    def __init__(self):
        self.document_id = None
        self.query_embedding = None
        self.top_k = None
        self.result = [
            RetrievedChunk(
                chunk_id=uuid.uuid4(),
                document_id=uuid.uuid4(),
                chunk_index=0,
                content="Noi dung lien quan",
                score=0.8,
            )
        ]

    def retrieve_chunks(self, *, document_id, query_embedding, top_k):
        self.document_id = document_id
        self.query_embedding = query_embedding
        self.top_k = top_k
        return self.result


class RetrievalServiceTestCase(unittest.TestCase):
    def test_retrieve_embeds_trimmed_question_and_passes_arguments(self):
        document_id = uuid.uuid4()
        fake_repo = FakeRetrievalRepository()
        service = RetrievalService(db=None, repository=fake_repo)

        result = service.retrieve(
            document_id=document_id,
            question="  FastAPI dung de lam gi?  ",
            top_k=3,
        )

        self.assertEqual(result, fake_repo.result)
        self.assertEqual(fake_repo.document_id, document_id)
        self.assertEqual(fake_repo.top_k, 3)
        self.assertEqual(len(fake_repo.query_embedding), EMBEDDING_DIM)
        self.assertGreater(sum(abs(value) for value in fake_repo.query_embedding), 0)

    def test_empty_question_is_rejected(self):
        service = RetrievalService(db=None, repository=FakeRetrievalRepository())

        with self.assertRaises(ValueError):
            service.retrieve(document_id=uuid.uuid4(), question="   ")

    def test_top_k_must_be_between_1_and_20(self):
        service = RetrievalService(db=None, repository=FakeRetrievalRepository())

        for top_k in (0, 21):
            with self.subTest(top_k=top_k):
                with self.assertRaises(ValueError):
                    service.retrieve(
                        document_id=uuid.uuid4(),
                        question="Cau hoi hop le",
                        top_k=top_k,
                    )


if __name__ == "__main__":
    unittest.main()
