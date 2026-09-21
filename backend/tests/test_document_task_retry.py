import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx
from celery.exceptions import Retry

from app.models.document import ProcessingStatus
from app.services.gemini_embedding_provider import GeminiEmbeddingProviderError
from app.tasks.document_processing import (
    handle_processing_failure,
    is_retryable_processing_error,
    retry_countdown,
)


class DocumentTaskRetryTestCase(unittest.TestCase):
    def test_classifies_only_transient_provider_and_http_errors_as_retryable(self):
        transient = GeminiEmbeddingProviderError("rate limited", retryable=True)
        permanent = GeminiEmbeddingProviderError("unauthorized", retryable=False)
        response_429 = httpx.Response(429, request=httpx.Request("POST", "https://example.test"))
        response_400 = httpx.Response(400, request=httpx.Request("POST", "https://example.test"))

        self.assertTrue(is_retryable_processing_error(transient))
        self.assertFalse(is_retryable_processing_error(permanent))
        self.assertTrue(
            is_retryable_processing_error(
                httpx.HTTPStatusError("429", request=response_429.request, response=response_429)
            )
        )
        self.assertFalse(
            is_retryable_processing_error(
                httpx.HTTPStatusError("400", request=response_400.request, response=response_400)
            )
        )
        self.assertFalse(is_retryable_processing_error(ValueError("invalid document")))

    @patch("app.tasks.document_processing.random.randint", return_value=0)
    def test_retry_delay_uses_capped_exponential_backoff(self, _randint):
        self.assertEqual([retry_countdown(i) for i in range(6)], [30, 60, 120, 240, 300, 300])

    @patch("app.tasks.document_processing.retry_countdown", return_value=60)
    def test_transient_failure_sets_retrying_before_scheduling_retry(self, _countdown):
        error = GeminiEmbeddingProviderError("temporary", retryable=True)
        task = Mock(
            request=SimpleNamespace(retries=1),
            max_retries=5,
        )
        task.retry.side_effect = Retry()
        repository = Mock()
        document = Mock()

        with self.assertRaises(Retry):
            handle_processing_failure(task, repository, document, error)

        repository.update_status.assert_called_once_with(
            document,
            ProcessingStatus.RETRYING,
            last_error="temporary",
        )
        task.retry.assert_called_once_with(exc=error, countdown=60)

    def test_permanent_failure_is_marked_failed_without_retry(self):
        error = ValueError("invalid document")
        task = Mock(request=SimpleNamespace(retries=0), max_retries=5)
        repository = Mock()
        document = Mock()

        with self.assertRaisesRegex(ValueError, "invalid document"):
            handle_processing_failure(task, repository, document, error)

        repository.update_status.assert_called_once_with(
            document,
            ProcessingStatus.FAILED,
            last_error="invalid document",
        )
        task.retry.assert_not_called()

    def test_exhausted_transient_failure_is_marked_failed(self):
        error = GeminiEmbeddingProviderError("still unavailable", retryable=True)
        task = Mock(request=SimpleNamespace(retries=5), max_retries=5)
        repository = Mock()
        document = Mock()

        with self.assertRaises(GeminiEmbeddingProviderError):
            handle_processing_failure(task, repository, document, error)

        repository.update_status.assert_called_once_with(
            document,
            ProcessingStatus.FAILED,
            last_error="still unavailable",
        )
        task.retry.assert_not_called()


if __name__ == "__main__":
    unittest.main()
