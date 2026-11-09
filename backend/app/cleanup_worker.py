"""Independent PostgreSQL polling process: python -m app.cleanup_worker."""

import logging
import json
from pathlib import Path
import signal
import threading
from typing import Callable

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.database import SessionLocal
from app.services.document_deletion_service import snapshot_storage_locator
from app.services.storage_cleanup_service import StorageCleanupService
from app.storage_certification import require_worker_enabled

logger = logging.getLogger(__name__)


def validate_startup(session_factory=SessionLocal) -> None:
    location = str(Path(settings.UPLOAD_DIR).resolve() / "startup-probe") if settings.STORAGE_BACKEND.lower() == "local" else "startup-probe"
    snapshot_storage_locator(location)
    with session_factory() as db:
        if db.get_bind().dialect.name != "postgresql":
            raise RuntimeError("Cleanup requires PostgreSQL")
        db.execute(text("SELECT 1 FROM storage_cleanup_jobs LIMIT 0"))
    if settings.CLEANUP_RETRY_BASE_SECONDS > settings.CLEANUP_RETRY_MAX_SECONDS:
        raise RuntimeError("Cleanup retry base exceeds maximum")
    if settings.STORAGE_BACKEND.lower() == "s3" and settings.CLEANUP_LEASE_SECONDS <= 4 * (
        settings.CLEANUP_CONNECT_TIMEOUT_SECONDS + settings.CLEANUP_READ_TIMEOUT_SECONDS
    ):
        raise RuntimeError("Cleanup lease must exceed the bounded S3 request budget")
    if settings.CLEANUP_SHUTDOWN_BUDGET_SECONDS <= 60 + 4 * (
        settings.CLEANUP_CONNECT_TIMEOUT_SECONDS + settings.CLEANUP_READ_TIMEOUT_SECONDS
    ):
        raise RuntimeError("Cleanup shutdown budget is insufficient")
    require_worker_enabled()
    # Actual bucket/capability validation uses the worker's credentials.
    from app.services.storage import S3Storage
    storage = S3Storage(cleanup=True)
    try:
        storage.validate_cleanup_target()
    finally:
        storage.client.close()


def run_worker(service: StorageCleanupService, stop: threading.Event, *, validator: Callable[[], None] | None = None) -> None:
    while not stop.is_set():
        try:
            if validator is not None:
                validator()
            service.run_once()
            if settings.CLEANUP_HEARTBEAT_FILE:
                Path(settings.CLEANUP_HEARTBEAT_FILE).touch()
        except Exception as exc:
            # No exception text/traceback: connection URLs and SDK messages can
            # contain credentials. The uncompleted lease remains in PostgreSQL.
            logger.error(json.dumps({"event": "cleanup_cycle_failed", "error_type": type(exc).__name__}))
        stop.wait(settings.CLEANUP_POLL_SECONDS)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    stop = threading.Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: stop.set())
    engine = None
    try:
        url = make_url(settings.DATABASE_URL)
        options = str(url.query.get("options", "")) + " -cstatement_timeout=15000 -clock_timeout=5000"
        engine = create_engine(url, pool_pre_ping=True, connect_args={
            "connect_timeout": max(1, int(settings.CLEANUP_CONNECT_TIMEOUT_SECONDS)), "options": options,
        })
        session_factory = sessionmaker(bind=engine, autoflush=False)
        validate_startup(session_factory)
    except Exception as exc:
        logger.error(json.dumps({"event": "cleanup_startup_failed", "error_type": type(exc).__name__}))
        if engine is not None:
            engine.dispose()
        raise SystemExit(1) from None
    try:
        logger.info(json.dumps({"event": "cleanup_worker_started"}))
        run_worker(StorageCleanupService(session_factory), stop, validator=require_worker_enabled)
    finally:
        engine.dispose()
        logger.info(json.dumps({"event": "cleanup_worker_stopped"}))


if __name__ == "__main__":
    main()
