"""Test-only bootstrap: real develop API/SQL/S3, deterministic external AI.

Run only via run-security-local.py on its disposable Docker network.
No production backend module is modified or copied from Fix 02.
"""
import os
import subprocess

assert os.environ.get("SECURITY_ISOLATED_TEST") == "1"
assert os.environ["DATABASE_URL"].endswith("@postgres:5432/security_next16")
assert os.environ["STORAGE_ENDPOINT_URL"] == "http://minio:9000"
assert os.environ["STORAGE_BUCKET"].startswith("security-next16-")

subprocess.run(["alembic", "upgrade", "head"], check=True)

import boto3  # noqa: E402
import uvicorn  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402
from app.services import document_service, retrieval_service  # noqa: E402
from app.services.gemini_provider import GeneratedAnswer, GeminiProvider  # noqa: E402


class FakeEmbeddings:
    def embed_batch(self, texts, **kwargs):
        return [[1.0] + [0.0] * 383 for _ in texts]

    def close(self):
        pass


def answer(self, *, question, context, history):
    return GeneratedAnswer(
        content="Isolated security regression answer.", grounded=True,
        source_chunk_indexes=[context[0].chunk_index],
    )


document_service.GeminiEmbeddingProvider = FakeEmbeddings
retrieval_service.GeminiEmbeddingProvider = FakeEmbeddings
document_service.generate_summary = lambda *args, **kwargs: "Security regression summary."
document_service.generate_suggested_questions = lambda *args, **kwargs: ["What is this document about?"]
GeminiProvider.answer = answer

boto3.client(
    "s3", endpoint_url=settings.STORAGE_ENDPOINT_URL,
    aws_access_key_id=settings.STORAGE_ACCESS_KEY_ID,
    aws_secret_access_key=settings.STORAGE_SECRET_ACCESS_KEY,
    region_name="us-east-1",
).create_bucket(Bucket=settings.STORAGE_BUCKET)
with SessionLocal() as db:
    db.add(User(
        full_name="Security Test Teacher", email="security.teacher@example.com",
        hashed_password=hash_password(os.environ["SECURITY_TEST_PASSWORD"]),
        role=UserRole.TEACHER,
    ))
    db.commit()

uvicorn.run(app, host="0.0.0.0", port=8000)
