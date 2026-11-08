"""Test-only hard crashes at transaction boundaries, never a production switch."""

import os
import re
import sys
import uuid

from sqlalchemy.engine import make_url


def main():
    if os.environ.get("RELIABILITY_FAULT_PROCESS") != "1":
        raise SystemExit("Dedicated test-process opt-in required")
    options = make_url(os.environ["DATABASE_URL"]).query.get("options", "")
    if not re.fullmatch(r"-csearch_path=cleanup_reliability_[0-9a-f]{32},public", options):
        raise SystemExit("Refusing fault injection outside an isolated M2 schema")
    from fastapi.testclient import TestClient
    from app.core.database import SessionLocal, get_db
    from app.core.security import create_access_token
    from app.main import app
    from app.models.document import Document
    from app.repositories.storage_cleanup_repo import StorageCleanupJobRepository
    from app.services.storage_cleanup_service import StorageCleanupService

    mode, identifier = sys.argv[1], uuid.UUID(sys.argv[2])
    if mode in {"api_before_commit", "api_after_commit"}:
        with SessionLocal() as db:
            document = db.get(Document, identifier)
            actor_id = document.uploaded_by
            db.rollback()
            commit = db.commit

            def crash():
                if mode == "api_after_commit":
                    commit()
                os._exit(71 if mode == "api_before_commit" else 72)

            db.commit = crash

            def override_db():
                yield db

            app.dependency_overrides[get_db] = override_db
            token = create_access_token(str(actor_id), "teacher")
            TestClient(app).delete(f"/documents/{identifier}", headers={"Authorization": "Bearer " + token})
    elif mode == "claim_before_commit":
        with SessionLocal() as db:
            StorageCleanupJobRepository(db).claim(120)
            os._exit(73)
    elif mode == "claim_after_commit":
        StorageCleanupService(SessionLocal).claim()
        os._exit(74)
    elif mode == "delete_before_done":
        service = StorageCleanupService(SessionLocal)

        def crash(*_, **__):
            os._exit(75)

        service.complete = crash
        service.run_once()
    raise SystemExit("Fault point was not reached")


if __name__ == "__main__":
    main()
