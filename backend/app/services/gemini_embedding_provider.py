from __future__ import annotations

from typing import Literal

import httpx

from app.core.config import settings


EmbeddingTaskType = Literal["RETRIEVAL_DOCUMENT", "RETRIEVAL_QUERY"]


class GeminiEmbeddingProviderError(Exception):
    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


class GeminiEmbeddingProvider:
    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        api_key: str | None = None,
        model: str | None = None,
        dimension: int | None = None,
        timeout_seconds: float | None = None,
    ):
        self._owns_client = client is None
        self.client = client or httpx.Client()
        self.api_key = settings.GEMINI_API_KEY if api_key is None else api_key
        configured_model = settings.GEMINI_EMBEDDING_MODEL if model is None else model
        self.model = configured_model.removeprefix("models/")
        self.dimension = settings.GEMINI_EMBEDDING_DIM if dimension is None else dimension
        self.timeout_seconds = (
            settings.GEMINI_TIMEOUT_SECONDS
            if timeout_seconds is None
            else timeout_seconds
        )

    def embed_batch(
        self,
        texts: list[str],
        *,
        task_type: EmbeddingTaskType,
    ) -> list[list[float]]:
        if not self.api_key.strip():
            raise GeminiEmbeddingProviderError("GEMINI_API_KEY chua duoc cau hinh.")
        if not self.model.strip():
            raise GeminiEmbeddingProviderError("GEMINI_EMBEDDING_MODEL chua duoc cau hinh.")
        if not texts:
            raise GeminiEmbeddingProviderError("Batch embedding khong duoc rong.")
        if task_type not in {"RETRIEVAL_DOCUMENT", "RETRIEVAL_QUERY"}:
            raise GeminiEmbeddingProviderError("Task type embedding khong hop le.")

        model_path = f"models/{self.model}"
        url = f"https://generativelanguage.googleapis.com/v1beta/{model_path}:batchEmbedContents"
        payload = {
            "requests": [
                {
                    "model": model_path,
                    "content": {"parts": [{"text": text}]},
                    "taskType": task_type,
                    "outputDimensionality": self.dimension,
                }
                for text in texts
            ]
        }

        try:
            response = self.client.post(
                url,
                params={"key": self.api_key},
                json=payload,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            body = response.json()
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise GeminiEmbeddingProviderError(
                "Gemini embedding network request failed.", retryable=True
            ) from exc
        except httpx.HTTPStatusError as exc:
            retryable = exc.response.status_code == 429 or exc.response.status_code >= 500
            raise GeminiEmbeddingProviderError(
                "Gemini embedding request failed.", retryable=retryable
            ) from exc
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise GeminiEmbeddingProviderError("Gemini embedding response is invalid.") from exc

        try:
            embeddings = body["embeddings"]
            values = [item["values"] for item in embeddings]
        except (KeyError, IndexError, TypeError):
            raise GeminiEmbeddingProviderError("Gemini embedding response is malformed.")

        if len(values) != len(texts):
            raise GeminiEmbeddingProviderError("Gemini returned an unexpected embedding count.")
        if any(
            not isinstance(vector, list)
            or len(vector) != self.dimension
            or not all(isinstance(value, (int, float)) for value in vector)
            for vector in values
        ):
            raise GeminiEmbeddingProviderError("Gemini returned an invalid embedding dimension.")
        return values

    def close(self) -> None:
        if self._owns_client:
            self.client.close()
