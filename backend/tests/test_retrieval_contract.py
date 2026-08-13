import unittest
import uuid

from app.schemas.retrieval import RetrievedChunk


class RetrievalContractTestCase(unittest.TestCase):
    def test_retrieved_chunk_is_immutable_and_exposes_required_fields(self):
        document_id = uuid.uuid4()
        chunk_id = uuid.uuid4()
        chunk = RetrievedChunk(
            chunk_id=chunk_id,
            document_id=document_id,
            chunk_index=2,
            content="Noi dung chunk",
            score=0.75,
        )

        self.assertEqual(chunk.chunk_id, chunk_id)
        self.assertEqual(chunk.document_id, document_id)
        self.assertEqual(chunk.chunk_index, 2)
        self.assertEqual(chunk.content, "Noi dung chunk")
        self.assertEqual(chunk.score, 0.75)
        with self.assertRaises(AttributeError):
            chunk.score = 1.0


if __name__ == "__main__":
    unittest.main()
