"""Explicit test-only provider overrides; real API, PostgreSQL, auth and storage."""
import os


def create_app():
    if os.getenv("RUN_OPERATIONAL_E2E") != "1" or os.getenv("ENV") != "test":
        raise RuntimeError("Operational fixture requires explicit isolated test environment")
    if not os.environ.get("DATABASE_URL", "").startswith("postgresql+psycopg2:"):
        raise RuntimeError("Operational fixture requires PostgreSQL")
    from app.main import app
    from app.api.routers.chat import get_answer_provider
    from app.services import document_service, retrieval_service, summary_service
    from app.services.gemini_provider import GeneratedAnswer
    from app.utils.text_extract import EMBEDDING_DIM

    class OfflineEmbedding:
        def embed_batch(self, texts, **_):
            return [[1.0] + [0.0] * (EMBEDDING_DIM - 1) for _ in texts]

        def close(self):
            pass

    class OfflineAnswer:
        def answer(self, *, question, context, history):
            return GeneratedAnswer(content="Local acceptance answer with retained evidence.", grounded=True,
                                   source_chunk_indexes=[chunk.chunk_index for chunk in context])

    document_service.GeminiEmbeddingProvider = OfflineEmbedding
    retrieval_service.GeminiEmbeddingProvider = OfflineEmbedding
    summary_service.gemini_provider.generate_text = lambda *_, **__: None
    app.dependency_overrides[get_answer_provider] = OfflineAnswer
    return app
