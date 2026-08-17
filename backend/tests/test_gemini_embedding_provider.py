import json
import unittest

import httpx

from app.services.gemini_embedding_provider import (
    GeminiEmbeddingProvider,
    GeminiEmbeddingProviderError,
)


class GeminiEmbeddingProviderTestCase(unittest.TestCase):
    @staticmethod
    def client(handler) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(handler))

    def test_batch_request_returns_ordered_384_dimensional_vectors(self):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["request"] = request
            captured["payload"] = json.loads(request.content)
            return httpx.Response(
                200,
                json={"embeddings": [{"values": [0.1] * 384}, {"values": [0.2] * 384}]},
            )

        provider = GeminiEmbeddingProvider(
            client=self.client(handler),
            api_key="test-key",
            model="models/gemini-embedding-001",
            dimension=384,
        )
        vectors = provider.embed_batch(
            ["chunk one", "chunk two"],
            task_type="RETRIEVAL_DOCUMENT",
        )

        self.assertEqual(vectors, [[0.1] * 384, [0.2] * 384])
        self.assertTrue(
            str(captured["request"].url).endswith(
                "/v1beta/models/gemini-embedding-001:batchEmbedContents?key=test-key"
            )
        )
        self.assertEqual(captured["payload"]["requests"][0]["taskType"], "RETRIEVAL_DOCUMENT")
        self.assertEqual(captured["payload"]["requests"][0]["outputDimensionality"], 384)
        self.assertEqual(
            captured["payload"]["requests"][1]["content"]["parts"][0]["text"],
            "chunk two",
        )

    def test_invalid_input_or_response_is_permanent_error(self):
        provider = GeminiEmbeddingProvider(
            client=self.client(lambda request: httpx.Response(200, json={})),
            api_key="key",
        )
        cases = (
            ([], "RETRIEVAL_DOCUMENT"),
            (["text"], "INVALID"),
        )
        for texts, task_type in cases:
            with self.subTest(texts=texts, task_type=task_type):
                with self.assertRaises(GeminiEmbeddingProviderError) as context:
                    provider.embed_batch(texts, task_type=task_type)
                self.assertFalse(context.exception.retryable)

        malformed_bodies = (
            {},
            {"embeddings": []},
            {"embeddings": [{"values": [0.1] * 383}]},
        )
        for body in malformed_bodies:
            with self.subTest(body=body):
                provider = GeminiEmbeddingProvider(
                    client=self.client(lambda request, body=body: httpx.Response(200, json=body)),
                    api_key="key",
                )
                with self.assertRaises(GeminiEmbeddingProviderError) as context:
                    provider.embed_batch(["text"], task_type="RETRIEVAL_QUERY")
                self.assertFalse(context.exception.retryable)

    def test_transient_http_and_network_errors_are_retryable(self):
        handlers = (
            lambda request: httpx.Response(429),
            lambda request: httpx.Response(500),
            lambda request: (_ for _ in ()).throw(httpx.ReadTimeout("timeout", request=request)),
            lambda request: (_ for _ in ()).throw(httpx.ConnectError("connection", request=request)),
        )
        for handler in handlers:
            with self.subTest(handler=handler):
                provider = GeminiEmbeddingProvider(client=self.client(handler), api_key="key")
                with self.assertRaises(GeminiEmbeddingProviderError) as context:
                    provider.embed_batch(["text"], task_type="RETRIEVAL_QUERY")
                self.assertTrue(context.exception.retryable)


if __name__ == "__main__":
    unittest.main()
