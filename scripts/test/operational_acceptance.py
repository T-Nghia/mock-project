"""Disposable real-backend/browser acceptance. Requires migrated test PG and S3.

Does not use SQLite, eager Celery, API interception, external AI or shared data.
"""
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request


ROOT = Path(__file__).resolve().parents[2]


def port():
    with socket.socket() as connection:
        connection.bind(("127.0.0.1", 0))
        return connection.getsockname()[1]


def ready(process, address, deadline=120):
    until = time.monotonic() + deadline
    while time.monotonic() < until:
        if process.poll() is not None:
            raise RuntimeError("Owned test server exited")
        try:
            with urllib.request.urlopen(address, timeout=2) as response:
                if response.status == 200:
                    return
        except OSError:
            pass
        time.sleep(0.2)
    raise RuntimeError("Owned test server readiness timed out")


def main():
    if os.getenv("ENV") != "test" or os.getenv("RUN_OPERATIONAL_E2E") != "1":
        raise RuntimeError("Explicit test opt-in required")
    if os.environ.get("DATABASE_URL") != os.environ.get("CLEANUP_TEST_DATABASE_URL"):
        raise RuntimeError("Use the dedicated migrated cleanup test database")
    sys.path.insert(0, str(ROOT / "backend"))
    from sqlalchemy import create_engine, select, text
    from sqlalchemy.engine import make_url
    from sqlalchemy.orm import sessionmaker
    from app.core.config import settings
    from app.core.database import Base
    from app.core.security import hash_password
    from app.models import user  # registers metadata
    from app.models.storage_cleanup import CleanupStatus, StorageCleanupJob
    from app.services.storage import S3Storage
    from app.storage_certification import certify_target
    import uuid

    token = uuid.uuid4().hex
    schema = "operational_e2e_" + token
    bucket = "slrms-m3-e2e-" + token
    api_port, closed_port, ui_port = port(), port(), port()
    url = make_url(settings.DATABASE_URL)
    engine = create_engine(url)
    artifacts = Path(os.getenv("M3_ARTIFACTS", str(ROOT / ".cache/fix02-m3/acceptance"))).resolve()
    artifacts.mkdir(parents=True, exist_ok=True)
    node = os.getenv("M3_NODE") or shutil.which("node")
    cli = Path(os.getenv("M3_PLAYWRIGHT_CLI", str(ROOT / "e2e/node_modules/@playwright/test/cli.js")))
    if not node or not cli.is_file():
        raise RuntimeError("Install existing frontend/e2e dependencies first")
    children, logs = [], []
    sessions_engine = None
    created_bucket = created_schema = False
    settings.STORAGE_BACKEND = "s3"
    settings.STORAGE_BUCKET = bucket
    storage = S3Storage(cleanup=True)

    def launch(name, args, env, cwd):
        stream = (artifacts / (name + ".log")).open("w", encoding="utf-8")
        logs.append(stream)
        process = subprocess.Popen(args, env=env, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                                   start_new_session=os.name != "nt")
        children.append(process)
        return process

    try:
        with engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        created_schema = True
        scoped = url.update_query_dict({"options": f"-csearch_path={schema},public"})
        sessions_engine = create_engine(scoped, execution_options={"schema_translate_map": {None: schema}})
        Base.metadata.create_all(sessions_engine)
        sessions = sessionmaker(bind=sessions_engine, autoflush=False)
        password = "Operational-Test-Only-2026!"
        with sessions() as db:
            for email in ("m3-owner@example.com", "m3-other@example.com"):
                db.add(user.User(email=email, full_name="M3 Test Teacher", hashed_password=hash_password(password),
                                 role=user.UserRole.TEACHER, is_active=True))
            db.commit()
        storage.client.create_bucket(Bucket=bucket)
        created_bucket = True
        certificate = certify_target()
        with tempfile.TemporaryDirectory(prefix="slrms-m3-acceptance-") as temporary:
            certificate_path = Path(temporary) / "certificate.json"
            certificate_path.write_text(json.dumps(certificate), encoding="utf-8")
            env = {**os.environ, "ENV": "test", "RUN_OPERATIONAL_E2E": "1",
                   "DATABASE_URL": scoped.render_as_string(hide_password=False),
                   "CLEANUP_ENABLED": "true", "DOCUMENT_DELETE_ENABLED": "true", "DOCUMENT_MUTATIONS_ENABLED": "true",
                   "CLEANUP_CERTIFICATE_FILE": str(certificate_path), "STORAGE_BACKEND": "s3", "STORAGE_BUCKET": bucket,
                   "CLEANUP_HEARTBEAT_FILE": str(Path(temporary) / "heartbeat"), "CLEANUP_POLL_SECONDS": "0.2",
                   "DOCUMENT_PROCESSING_MODE": "background", "REFRESH_COOKIE_SECURE": "false", "REFRESH_COOKIE_SAMESITE": "lax",
                   "AUTH_RATE_LIMIT_ENABLED": "false", "NEXT_TELEMETRY_DISABLED": "1",
                   "OPENAI_API_KEY": "", "ANTHROPIC_API_KEY": "", "GEMINI_API_KEY": "",
                   "APP_URL": f"http://localhost:{ui_port}", "API_URL": f"http://localhost:{api_port}",
                   "M3_CLOSED_API_URL": f"http://localhost:{closed_port}", "NEXT_PUBLIC_API_URL": f"http://localhost:{api_port}",
                   "CORS_ORIGINS": json.dumps([f"http://localhost:{ui_port}"]),
                   "SMOKE_EMAIL": "m3-owner@example.com", "SMOKE_PASSWORD": password}
            backend = [sys.executable, "-m", "uvicorn", "tests.integration.operational_server:create_app", "--factory", "--host", "127.0.0.1"]
            opened = launch("api-open", [*backend, "--port", str(api_port)], env, ROOT / "backend")
            closed = launch("api-closed", [*backend, "--port", str(closed_port)],
                            {**env, "DOCUMENT_DELETE_ENABLED": "false", "DOCUMENT_MUTATIONS_ENABLED": "false"}, ROOT / "backend")
            worker = launch("cleanup", [sys.executable, "-m", "app.cleanup_worker"], env, ROOT / "backend")
            ready(opened, env["API_URL"] + "/health/live")
            ready(closed, env["M3_CLOSED_API_URL"] + "/health/live")
            # Production build avoids development-only StrictMode effect replay
            # and binds NEXT_PUBLIC_API_URL to this disposable backend.
            build = launch("frontend-build", [node, "node_modules/next/dist/bin/next", "build"], env, ROOT / "frontend")
            if build.wait(300) != 0:
                raise RuntimeError("Owned frontend build failed")
            frontend = launch("frontend", [node, "node_modules/next/dist/bin/next", "start", "--hostname", "127.0.0.1", "--port", str(ui_port)], env, ROOT / "frontend")
            ready(frontend, env["APP_URL"] + "/login")
            result = subprocess.run([node, str(cli), "test", "tests/storage-operational.spec.js", "--reporter=json", "--retries=0"],
                                    cwd=ROOT / "e2e", env=env, capture_output=True, text=True, encoding="utf-8", timeout=180)
            (artifacts / "playwright.json").write_text(result.stdout, encoding="utf-8")
            (artifacts / "playwright.stderr").write_text(result.stderr, encoding="utf-8")
            report = json.loads(result.stdout)
            stats = report["stats"]
            print(json.dumps({"browser_stats": stats}))
            if result.returncode or stats["expected"] != 2 or stats["skipped"] or stats["unexpected"]:
                raise RuntimeError("Real-backend browser acceptance failed or skipped")
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if worker.poll() is not None:
                    raise RuntimeError("Owned cleanup worker exited")
                with sessions() as db:
                    jobs = list(db.scalars(select(StorageCleanupJob)))
                    done = len(jobs) == 2 and all(job.status == CleanupStatus.DONE for job in jobs)
                if done:
                    break
                time.sleep(0.2)
            else:
                raise RuntimeError("Cleanup did not complete both real API jobs")
            remaining = storage.client.list_objects_v2(Bucket=bucket).get("KeyCount", 0)
            if remaining:
                raise RuntimeError("Objects remain after acknowledged cleanup completion")
            print("PASS: real browser/API/PG/MinIO, retained citations/private transcript, gates, two DONE jobs and zero remaining objects")
    finally:
        # Only PIDs returned by our Popen calls, never a user process/port search.
        for process in reversed(children):
            if os.name == "nt":
                if process.poll() is None:
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, check=True)
            else:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            try:
                process.wait(180)
            except subprocess.TimeoutExpired:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, check=True)
                else:
                    os.killpg(process.pid, signal.SIGKILL)
                process.wait(15)
        for stream in logs:
            stream.close()
        if sessions_engine is not None:
            sessions_engine.dispose()
        if created_schema:
            assert re.fullmatch(r"operational_e2e_[0-9a-f]{32}", schema)
            with engine.begin() as connection:
                connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        engine.dispose()
        if created_bucket:
            assert re.fullmatch(r"slrms-m3-e2e-[0-9a-f]{32}", bucket)
            for item in storage.client.list_objects_v2(Bucket=bucket).get("Contents", []):
                storage.client.delete_object(Bucket=bucket, Key=item["Key"])
            storage.client.delete_bucket(Bucket=bucket)
        storage.client.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"error": "operational_acceptance_failed", "error_type": type(exc).__name__}), file=sys.stderr)
        raise SystemExit(1)
