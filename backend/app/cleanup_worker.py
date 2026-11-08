"""Independent PostgreSQL polling process: python -m app.cleanup_worker."""

import logging
from pathlib import Path
import signal
import threading

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.database import SessionLocal
from app.services.document_deletion_service import snapshot_storage_locator
from app.services.storage_cleanup_service import StorageCleanupService

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


def run_worker(service: StorageCleanupService, stop: threading.Event) -> None:
    while not stop.is_set():
        try:
            service.run_once()
        except Exception as exc:
            # No exception text/traceback: connection URLs and SDK messages can
            # contain credentials. The uncompleted lease remains in PostgreSQL.
            logger.error("event=cleanup_cycle_failed error_type=%s", type(exc).__name__)
        stop.wait(settings.CLEANUP_POLL_SECONDS)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
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
        logger.error("event=cleanup_startup_failed error_type=%s", type(exc).__name__)
        if engine is not None:
            engine.dispose()
        raise SystemExit(1) from None
    try:
        run_worker(StorageCleanupService(session_factory), stop)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
