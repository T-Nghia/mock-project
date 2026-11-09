"""Disposable real-backend browser rehearsal; requires Docker, Node and npm.

Build backend/frontend images first; pass their local tags explicitly. All data
is tmpfs, all resources have a fresh ownership label, all published ports bind
loopback. Existing containers, buckets, images and volumes are never removed.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import signal
import shutil
import socket
import subprocess
import time
import urllib.request
import uuid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-image", required=True)
    parser.add_argument("--frontend-image", required=True)
    parser.add_argument("--frontend-mode", choices=("production", "development"), default="production")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    evidence = root / ".cache/frontend-security-next16" / ("real-backend" if args.frontend_mode == "production" else "real-backend-development")
    evidence.mkdir(parents=True, exist_ok=True)
    for port in (3000, 8000):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))
    marker = "next16-" + uuid.uuid4().hex[:12]
    label = "slrms.security-test=" + marker
    password = secrets.token_urlsafe(24)
    containers = []
    network = None
    frontend_process = None
    frontend_log = None

    def docker(*parts, **kwargs):
        result = subprocess.run(["docker", *parts], text=True, capture_output=True, **kwargs)
        if result.returncode:
            raise RuntimeError(result.stderr.replace(password, "[REDACTED]"))
        return result.stdout.strip()

    def start(name, image, options, command=()):
        cid = docker("create", "--name", marker + "-" + name,
                     "--label", label, "--network", marker, "--network-alias", name,
                     *options, image, *command)
        containers.append(cid)
        docker("start", cid)
        return cid

    def ready(url):
        deadline = time.monotonic() + 90
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        while time.monotonic() < deadline:
            try:
                with opener.open(url, timeout=2) as response:
                    if response.status == 200:
                        return
            except (OSError, TimeoutError):
                time.sleep(1)
        raise RuntimeError("Readiness deadline exceeded: " + url)

    try:
        network = docker("network", "create", "--label", label, marker)
        pg = start("postgres", "pgvector/pgvector:pg16", [
            "--tmpfs", "/var/lib/postgresql/data:rw,size=512m",
            "-e", "POSTGRES_DB=security_next16", "-e", "POSTGRES_USER=security",
            "-e", "POSTGRES_PASSWORD=" + password,
        ])
        for _ in range(60):
            if subprocess.run(["docker", "exec", pg, "pg_isready", "-U", "security"],
                              capture_output=True).returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError("PostgreSQL readiness deadline exceeded")
        start("redis", "redis:7-alpine", ["--tmpfs", "/data:rw,size=32m"])
        start("minio", "cgr.dev/chainguard/minio@sha256:3b6e40c30ecd5cea627e382ff0b82ca841f58c52294578787043ee80c8ef7c82", [
            "--tmpfs", "/data:rw,uid=65532,gid=65532,mode=0700,size=512m",
            "-e", "MINIO_ROOT_USER=security-test", "-e", "MINIO_ROOT_PASSWORD=" + password,
            "-e", "MINIO_BROWSER=off",
        ], ["server", "/data", "--address", ":9000"])
        # The backend bootstrap creates the bucket; boto3 retries transient startup.
        env = {
            "SECURITY_ISOLATED_TEST": "1", "ENV": "test",
            "DATABASE_URL": f"postgresql+psycopg2://security:{password}@postgres:5432/security_next16",
            "REDIS_URL": "redis://redis:6379/0",
            "JWT_SECRET_KEY": secrets.token_urlsafe(48), "AUTH_RATE_LIMIT_ENABLED": "false",
            "STORAGE_BACKEND": "s3", "STORAGE_BUCKET": "security-" + marker,
            "STORAGE_ENDPOINT_URL": "http://minio:9000", "STORAGE_REGION": "us-east-1",
            "STORAGE_ACCESS_KEY_ID": "security-test", "STORAGE_SECRET_ACCESS_KEY": password,
            "SECURITY_TEST_PASSWORD": password, "DOCUMENT_PROCESSING_MODE": "background",
            "CORS_ORIGINS": '["http://localhost:3000"]', "PYTHONDONTWRITEBYTECODE": "1",
            "UPLOAD_DIR": "/tmp/security-uploads",
            "PYTHONPATH": "/app", "GEMINI_API_KEY": "", "OPENAI_API_KEY": "",
        }
        options = ["--publish", "127.0.0.1:8000:8000", "--tmpfs", "/tmp:rw,mode=1777",
                   "--mount", f"type=bind,source={root / 'backend'},target=/app,readonly",
                   "--mount", f"type=bind,source={root / 'e2e/fixtures'},target=/test-support,readonly",
                   "--entrypoint", "python"]
        for key, value in env.items():
            options += ["--env", f"{key}={value}"]
        start("backend", args.backend_image, options, ["/test-support/security_backend.py"])
        ready("http://localhost:8000/health/ready")
        if args.frontend_mode == "production":
            start("frontend", args.frontend_image, ["--publish", "127.0.0.1:3000:3000"])
        else:
            npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
            frontend_log = (evidence / "next-dev.log").open("w", encoding="utf-8")
            options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
            frontend_process = subprocess.Popen(
                [npm, "run", "dev", "--", "--hostname", "127.0.0.1"], cwd=root / "frontend",
                env=dict(os.environ, NEXT_TELEMETRY_DISABLED="1"), stdout=frontend_log, stderr=subprocess.STDOUT,
                **options,
            )
        ready("http://localhost:3000/login")
        test_env = dict(os.environ, APP_URL="http://localhost:3000", API_URL="http://localhost:8000",
                        SECURITY_ISOLATED_TEST="1", SECURITY_TEST_PASSWORD=password)
        npx = shutil.which("npx.cmd" if os.name == "nt" else "npx")
        with (evidence / "playwright.json").open("w", encoding="utf-8") as output:
            result = subprocess.run([npx, "playwright", "test", "--config", "playwright.real.config.js",
                                     "--reporter=json"], cwd=root / "e2e", env=test_env, stdout=output)
        if result.returncode:
            raise RuntimeError("Real-backend browser suite failed; inspect isolated evidence")
        stats = json.loads((evidence / "playwright.json").read_text(encoding="utf-8"))["stats"]
        if stats["expected"] != 2 or stats["skipped"] or stats["unexpected"] or stats["flaky"]:
            raise RuntimeError("Both real-backend tests must pass without skips or flaky retries")
        print("Real PostgreSQL/MinIO/backend browser acceptance: PASS")
    finally:
        if frontend_process:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(frontend_process.pid), "/T", "/F"], capture_output=True)
            else:
                os.killpg(frontend_process.pid, signal.SIGTERM)
            frontend_process.wait(timeout=15)
            frontend_log.close()
        removed = []
        for cid in reversed(containers):
            info = json.loads(docker("inspect", cid))[0]
            assert info["Config"]["Labels"].get("slrms.security-test") == marker
            log = subprocess.run(["docker", "logs", cid], capture_output=True, text=True)
            (evidence / (info["Name"].lstrip("/") + ".log")).write_text(
                (log.stdout + log.stderr).replace(password, "[REDACTED]"), encoding="utf-8")
            docker("rm", "--force", cid)
            removed.append(cid)
        if network:
            info = json.loads(docker("network", "inspect", network))[0]
            assert info["Labels"].get("slrms.security-test") == marker
            docker("network", "rm", network)
        (evidence / "cleanup.json").write_text(json.dumps({"marker": marker, "removed": removed,
                                                         "network_removed": bool(network)}, indent=2))
        print("Disposable resources removed:", len(removed), "containers; network:", bool(network))


if __name__ == "__main__":
    main()
