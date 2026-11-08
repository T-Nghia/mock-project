"""Dedicated PostgreSQL schemas and subprocess environment for M2 evidence."""

import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace
import unittest
import uuid
from unittest.mock import patch

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.database import Base
from app.models.document import Document, ProcessingStatus
from app.models.storage_cleanup import StorageCleanupJob
from app.models.user import User, UserRole
from app.services.document_deletion_service import DocumentDeletionService
from app.services.storage_cleanup_service import StorageCleanupService


class ReliabilityDatabaseCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_url = os.environ.get("RELIABILITY_TEST_DATABASE_URL") or os.environ["CLEANUP_TEST_DATABASE_URL"]
        cls.admin_engine = create_engine(cls.database_url)
        cls.addClassCleanup(cls.admin_engine.dispose)
        if (cls.admin_engine.dialect.name, cls.admin_engine.dialect.driver) != ("postgresql", "psycopg2"):
            raise RuntimeError("M2 evidence requires a dedicated PostgreSQL/psycopg2 database")

    def setUp(self):
        self.schema = "cleanup_reliability_" + uuid.uuid4().hex
        with self.admin_engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{self.schema}"'))
        self.addCleanup(self.drop_schema)
        self.engine = create_engine(
            self.database_url, connect_args={"options": f"-csearch_path={self.schema},public"},
            execution_options={"schema_translate_map": {None: self.schema}},
        )
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine, autoflush=False)
        self.storage_settings = patch.multiple(
            settings, STORAGE_BACKEND="s3", STORAGE_BUCKET="fix02-m2-" + uuid.uuid4().hex,
            STORAGE_ENDPOINT_URL=os.getenv("STORAGE_ENDPOINT_URL", "http://127.0.0.1:19000"),
            STORAGE_REGION="us-east-1",
        )
        self.storage_settings.start()
        self.addCleanup(self.storage_settings.stop)
        with self.sessions() as db:
            owner = User(full_name="M2 Owner", email=f"{uuid.uuid4()}@example.com",
                         hashed_password="unused", role=UserRole.TEACHER, is_active=True)
            db.add(owner)
            db.flush()
            self.actor = SimpleNamespace(id=owner.id, role=owner.role)
            self.key = uuid.uuid4().hex + ".txt"
            document = Document(title="M2 Test", uploaded_by=owner.id, file_path=self.key,
                                file_type="txt", processing_status=ProcessingStatus.PENDING)
            db.add(document)
            db.flush()
            self.document_id = document.id
            db.commit()
        self.service = StorageCleanupService(self.sessions)

    def drop_schema(self):
        self.assertRegex(self.schema, r"^cleanup_reliability_[0-9a-f]{32}$")
        with self.admin_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{self.schema}" CASCADE'))

    def queue_delete(self, document_id=None):
        with self.sessions() as db:
            DocumentDeletionService(db).delete_document(document_id or self.document_id, self.actor)
        with self.sessions() as db:
            return db.scalar(select(StorageCleanupJob.id).where(
                StorageCleanupJob.document_id == (document_id or self.document_id),
            ))

    def job(self, job_id):
        with self.sessions() as db:
            row = db.get(StorageCleanupJob, job_id)
            db.expunge(row)
            return row

    def expire(self, job_id):
        with self.engine.begin() as connection:
            connection.execute(text("UPDATE storage_cleanup_jobs SET lease_expires_at = clock_timestamp() - interval '1 second' WHERE id = :id"), {"id": job_id})

    def due(self, job_id):
        with self.engine.begin() as connection:
            connection.execute(text("UPDATE storage_cleanup_jobs SET next_attempt_at = clock_timestamp() - interval '1 second' WHERE id = :id"), {"id": job_id})

    def count(self, model):
        with self.sessions() as db:
            return db.scalar(select(func.count()).select_from(model))

    def child_environment(self):
        url = make_url(self.database_url).update_query_dict({"options": f"-csearch_path={self.schema},public"})
        return {
            **os.environ, "DATABASE_URL": url.render_as_string(hide_password=False),
            "ENV": "test", "RELIABILITY_FAULT_PROCESS": "1", "PYTHONDONTWRITEBYTECODE": "1",
            "STORAGE_BACKEND": settings.STORAGE_BACKEND, "STORAGE_BUCKET": settings.STORAGE_BUCKET,
            "STORAGE_ENDPOINT_URL": settings.STORAGE_ENDPOINT_URL, "STORAGE_REGION": settings.STORAGE_REGION,
            "STORAGE_ACCESS_KEY_ID": settings.STORAGE_ACCESS_KEY_ID,
            "STORAGE_SECRET_ACCESS_KEY": settings.STORAGE_SECRET_ACCESS_KEY,
            "JWT_SECRET_KEY": settings.JWT_SECRET_KEY,
            "OPENAI_API_KEY": "", "ANTHROPIC_API_KEY": "", "GEMINI_API_KEY": "",
        }

    def fault_process(self, mode, identifier):
        return subprocess.run(
            [sys.executable, "-m", "tests.integration.reliability_fault_process", mode, str(identifier)],
            cwd=Path(__file__).resolve().parents[2], env=self.child_environment(),
            capture_output=True, text=True, timeout=30,
        )

    def wait_for_lock(self, pid, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self.admin_engine.connect() as connection:
                waiting = connection.scalar(text("SELECT wait_event_type = 'Lock' FROM pg_stat_activity WHERE pid = :pid"), {"pid": pid})
            if waiting:
                return
            time.sleep(0.01)
        self.fail("PostgreSQL never reported the expected synchronization lock")
