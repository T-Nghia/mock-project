import json
import unittest
import uuid

import httpx

from app.schemas.retrieval import RetrievedChunk
from app.services.gemini_provider import (
    GeneratedAnswer,
    GeminiProvider,
    GeminiProviderError,
)


class GeminiProviderTestCase(unittest.TestCase):
    @staticmethod
    def chunk() -> RetrievedChunk:
        return RetrievedChunk(
            chunk_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            chunk_index=0,
            content="Python la ngon ngu lap trinh.",
            score=0.9,
        )

    @staticmethod
    def client(handler) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(handler))

    def test_answer_sends_grounded_prompt_and_parses_structured_response(self):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["request"] = request
            captured["payload"] = json.loads(request.content)
            return httpx.Response(
                200,
                json={
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {
                                        "text": json.dumps(
                                            {
                                                "content": "Python dung de lap trinh.",
                                                "grounded": True,
                                                "source_chunk_indexes": [0],
                                            }
                                        )
                                    }
                                ]
                            }
                        }
                    ]
                },
            )

        provider = GeminiProvider(
            client=self.client(handler),
            api_key="test-key",
            model="test-model",
            timeout_seconds=5,
        )

        answer = provider.answer(
            question="Python dung de lam gi?",
            context=[self.chunk()],
            history=[],
        )

        self.assertEqual(
            answer,
            GeneratedAnswer(content="Python dung de lap trinh.", grounded=True, source_chunk_indexes=[0]),
        )
        request = captured["request"]
        self.assertIn("/v1beta/models/test-model:generateContent", str(request.url))
        self.assertEqual(request.url.params["key"], "test-key")
        prompt = captured["payload"]["contents"][0]["parts"][0]["text"]
        system_instruction = captured["payload"]["systemInstruction"]["parts"][0]["text"]
        self.assertIn("Chỉ trả lời dựa trên CONTEXT", system_instruction)
        self.assertIn("không đáng tin", system_instruction)
        self.assertIn("Không tạo citation", system_instruction)
        self.assertIn("Python la ngon ngu lap trinh.", prompt)
        self.assertIn("Python dung de lam gi?", prompt)

    def test_answer_rejects_missing_api_key_or_model(self):
        for api_key, model in (("", "model"), ("key", "")):
            with self.subTest(api_key=bool(api_key), model=bool(model)):
                provider = GeminiProvider(
                    client=self.client(lambda request: httpx.Response(200)),
                    api_key=api_key,
                    model=model,
                )
                with self.assertRaises(GeminiProviderError):
                    provider.answer(
                        question="Question",
                        context=[self.chunk()],
                        history=[],
                    )

    def test_answer_maps_http_and_timeout_failures(self):
        def timeout_handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("timeout", request=request)

        handlers = (
            lambda request: httpx.Response(429, json={"error": "quota"}),
            lambda request: httpx.Response(500, json={"error": "server"}),
            timeout_handler,
        )
        for handler in handlers:
            with self.subTest(handler=handler):
                provider = GeminiProvider(
                    client=self.client(handler),
                    api_key="key",
                    model="model",
                )
                with self.assertRaises(GeminiProviderError):
                    provider.answer(
                        question="Question",
                        context=[self.chunk()],
                        history=[],
                    )

    def test_answer_rejects_malformed_provider_response(self):
        responses = (
            {},
            [],
            "text",
            {"candidates": [{"content": {"parts": []}}]},
            {"candidates": [{"content": {"parts": [{"text": "not-json"}]}}]},
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": json.dumps({"content": "missing flag"})}]
                        }
                    }
                ]
            },
        )
        for body in responses:
            with self.subTest(body=body):
                provider = GeminiProvider(
                    client=self.client(lambda request, body=body: httpx.Response(200, json=body)),
                    api_key="key",
                    model="model",
                )
                with self.assertRaises(GeminiProviderError):
                    provider.answer(
                        question="Question",
                        context=[self.chunk()],
                        history=[],
                    )

    def test_answer_accepts_empty_content_when_response_is_ungrounded(self):
        body = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": json.dumps(
                    {"content": "", "grounded": False, "source_chunk_indexes": []}
                                )
                            }
                        ]
                    }
                }
            ]
        }
        provider = GeminiProvider(
            client=self.client(lambda request: httpx.Response(200, json=body)),
            api_key="key",
            model="model",
        )

        answer = provider.answer(
            question="Question",
            context=[self.chunk()],
            history=[],
        )

        self.assertEqual(answer, GeneratedAnswer(content="", grounded=False, source_chunk_indexes=[]))

    def test_close_releases_owned_http_client(self):
        provider = GeminiProvider(api_key="key", model="model")

        provider.close()

        self.assertTrue(provider.client.is_closed)


if __name__ == "__main__":
    unittest.main()
