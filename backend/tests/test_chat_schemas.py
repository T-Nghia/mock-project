import unittest
import uuid
from datetime import datetime, timezone

from pydantic import ValidationError

from app.schemas.chat import (
    ChatAnswerResponse,
    ChatCitation,
    ChatMessageResponse,
    ChatQuestionRequest,
    ChatSessionCreate,
    ChatSessionDetailResponse,
    ChatSessionResponse,
)


class ChatSchemasTestCase(unittest.TestCase):
    def test_question_is_trimmed(self):
        request = ChatQuestionRequest(content="  Bien trong Python la gi?  ")

        self.assertEqual(request.content, "Bien trong Python la gi?")

    def test_question_rejects_empty_or_too_long_content(self):
        for content in ("   ", "x" * 4001):
            with self.subTest(length=len(content)):
                with self.assertRaises(ValidationError):
                    ChatQuestionRequest(content=content)

    def test_question_length_is_checked_after_trimming(self):
        request = ChatQuestionRequest(content=f"  {'x' * 4000}  ")

        self.assertEqual(len(request.content), 4000)

    def test_input_schemas_reject_extra_fields_and_invalid_document_id(self):
        with self.assertRaises(ValidationError):
            ChatSessionCreate(document_id="not-a-uuid")

        with self.assertRaises(ValidationError):
            ChatQuestionRequest(content="Cau hoi", document_id=str(uuid.uuid4()))

    def test_chat_responses_serialize_required_fields(self):
        now = datetime.now(timezone.utc)
        session_id = uuid.uuid4()
        document_id = uuid.uuid4()
        message_id = uuid.uuid4()
        chunk_id = uuid.uuid4()
        citation = ChatCitation(
            chunk_id=chunk_id,
            chunk_index=2,
            quote="Bien la vung nho dung de luu du lieu.",
            score=0.82,
        )
        user_message = ChatMessageResponse(
            id=message_id,
            role="user",
            content="Bien la gi?",
            sources=[],
            created_at=now,
        )
        session = ChatSessionDetailResponse(
            id=session_id,
            document_id=document_id,
            title="New chat",
            created_at=now,
            messages=[user_message],
        )
        answer = ChatAnswerResponse(
            answer="Theo tai lieu, bien la vung nho.",
            sources=[citation],
        )

        session_json = session.model_dump(mode="json")
        answer_json = answer.model_dump(mode="json")
        self.assertEqual(session_json["id"], str(session_id))
        self.assertEqual(session_json["document_id"], str(document_id))
        self.assertEqual(session_json["messages"][0]["sources"], [])
        self.assertEqual(answer_json["sources"][0]["chunk_id"], str(chunk_id))
        self.assertEqual(answer_json["sources"][0]["chunk_index"], 2)
        self.assertEqual(answer_json["sources"][0]["score"], 0.82)

        summary = ChatSessionResponse(
            id=session_id,
            document_id=document_id,
            title="New chat",
            created_at=now,
        )
        self.assertEqual(summary.document_id, document_id)


if __name__ == "__main__":
    unittest.main()
