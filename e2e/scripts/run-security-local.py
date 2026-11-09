"""Disposable real-backend browser rehearsal; requires Docker, Node and npm.

Build backend/frontend images first; pass their local tags explicitly. All data
is tmpfs, all resources have a fresh ownership label, all published ports bind
loopback. Existing containers, buckets, images and volumes are never removed.
"""
import argparse
import json
import os
from pathlib import Path
import re
import secrets
import signal
import shutil
import socket
import subprocess
import time
import urllib.request
import uuid


MAX_LOG_BYTES = 32 * 1024


def sanitize(text, secret_values=()):
    for value in secret_values:
        if value:
            text = text.replace(value, "[REDACTED]")
    text = re.sub(r"\beyJ[\w-]+\.[\w-]+\.[\w-]+\b", "[REDACTED_JWT]", text)
    return re.sub(r"(?i)\bBearer\s+[\w.~+/-]+", "Bearer [REDACTED]", text)


def docker(*parts, secret_values=()):
    try:
        result = subprocess.run(["docker", *parts], text=True, encoding="utf-8", errors="replace",
                                capture_output=True, timeout=120)
    except subprocess.TimeoutExpired:
        # TimeoutExpired includes argv, which can contain test credentials.
        raise RuntimeError("Docker command timed out: " + parts[0]) from None
    if result.returncode:
        raise RuntimeError(sanitize(result.stderr[-MAX_LOG_BYTES:], secret_values))
    return result.stdout.strip()


def validate_owner(info, marker, network=False):
    if not re.fullmatch(r"next16-[0-9a-f]{12}", marker):
        raise RuntimeError("Invalid fixture ownership marker")
    labels = info.get("Labels", {}) if network else info.get("Config", {}).get("Labels", {})
    name = info.get("Name", "").lstrip("/")
    expected_name = name == marker if network else name.startswith(marker + "-")
    if labels.get("slrms.security-test") != marker or not expected_name:
        raise RuntimeError("Fixture ownership mismatch; resource was not removed")


def cleanup_owned(marker, evidence, secret_values=(), capture_logs=True, filename="cleanup.json"):
    if not re.fullmatch(r"next16-[0-9a-f]{12}", marker):
        raise RuntimeError("Invalid fixture ownership marker")
    selector = "label=slrms.security-test=" + marker
    removed, networks, errors = [], [], []
    # Discover by this run's marker, including a create interrupted before journaling its ID.
    for cid in docker("ps", "--all", "--quiet", "--filter", selector).split():
        try:
            info = json.loads(docker("inspect", cid))[0]
            validate_owner(info, marker)
            if capture_logs:
                try:
                    log = subprocess.run(["docker", "logs", "--tail", "200", cid],
                                         capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15)
                    if log.returncode:
                        errors.append("Container log capture failed: " + cid)
                    text = sanitize(log.stdout + log.stderr, secret_values)
                    bounded = text.encode("utf-8")[-MAX_LOG_BYTES:].decode("utf-8", errors="ignore")
                    (evidence / (info["Name"].lstrip("/") + ".log")).write_text(bounded, encoding="utf-8")
                except subprocess.TimeoutExpired:
                    errors.append("Container log capture timed out: " + cid)
                except Exception as exc:
                    errors.append("Container log capture failed: " + cid + " (" + type(exc).__name__ + "): "
                                  + sanitize(str(exc), secret_values))
            docker("rm", "--force", cid)
            removed.append(cid)
        except Exception as exc:
            errors.append(sanitize(str(exc), secret_values))
    for nid in docker("network", "ls", "--quiet", "--filter", selector).split():
        try:
            info = json.loads(docker("network", "inspect", nid))[0]
            validate_owner(info, marker, network=True)
            docker("network", "rm", nid)
            networks.append(nid)
        except Exception as exc:
            errors.append(sanitize(str(exc), secret_values))
    result = {"marker": marker, "removed": removed, "networks_removed": networks, "errors": errors}
    (evidence / filename).write_text(json.dumps(result, indent=2), encoding="utf-8")
    if errors:
        raise RuntimeError("Fixture cleanup failed: " + "; ".join(errors))
    return result


def journal_marker(journal):
    if not isinstance(journal, dict) or set(journal) != {"marker", "containers", "network"}:
        raise RuntimeError("Invalid fixture journal schema; journal retained")
    marker = journal["marker"]
    if not isinstance(marker, str) or not re.fullmatch(r"next16-[0-9a-f]{12}", marker):
        raise RuntimeError("Invalid fixture journal marker; journal retained")
    if not isinstance(journal["containers"], list) or not all(isinstance(cid, str) for cid in journal["containers"]):
        raise RuntimeError("Invalid fixture journal container IDs; journal retained")
    if journal["network"] is not None and not isinstance(journal["network"], str):
        raise RuntimeError("Invalid fixture journal network ID; journal retained")
    return marker


def write_journal(path, journal, initial=False):
    marker = journal_marker(journal)
    if initial:
        try:
            # Exclusive creation prevents a new normal run from overwriting an
            # interrupted run, even between the existence check and file open.
            with path.open("x", encoding="utf-8") as output:
                json.dump(journal, output, indent=2)
        except FileExistsError:
            raise RuntimeError("Existing fixture journal; run --cleanup-only before starting another run") from None
        return
    current = json.loads(path.read_text(encoding="utf-8"))
    if journal_marker(current) != marker:
        raise RuntimeError("Fixture journal owner changed; refusing overwrite")
    temporary = path.with_name("resources-" + marker + ".tmp")
    temporary.write_text(json.dumps(journal, indent=2), encoding="utf-8")
    if journal_marker(json.loads(path.read_text(encoding="utf-8"))) != marker:
        raise RuntimeError("Fixture journal owner changed; refusing overwrite")
    temporary.replace(path)


def retire_journal(path, marker):
    if journal_marker(json.loads(path.read_text(encoding="utf-8"))) != marker:
        raise RuntimeError("Fixture journal owner changed; journal retained")
    selector = "label=slrms.security-test=" + marker
    containers = docker("ps", "--all", "--quiet", "--filter", selector)
    networks = docker("network", "ls", "--quiet", "--filter", selector)
    if containers or networks:
        raise RuntimeError("Owned fixture resources remain; journal retained for --cleanup-only")
    if journal_marker(json.loads(path.read_text(encoding="utf-8"))) != marker:
        raise RuntimeError("Fixture journal owner changed; journal retained")
    archive = path.with_name("resources-" + marker + "-" + uuid.uuid4().hex + ".json")
    path.rename(archive)
    return archive


def recover_journal(path, evidence):
    if not path.exists():
        (evidence / "fallback-cleanup.json").write_text(
            json.dumps({"status": "NOT RUN", "reason": "No active fixture journal; nothing to recover"}),
            encoding="utf-8",
        )
        return
    marker = journal_marker(json.loads(path.read_text(encoding="utf-8")))
    # No credentials are persisted. Recovery cannot safely capture logs from a
    # previous process without its in-memory redaction values.
    result = cleanup_owned(marker, evidence, capture_logs=False, filename="fallback-cleanup.json")
    result["journal_archive"] = retire_journal(path, marker).name
    (evidence / "fallback-cleanup.json").write_text(json.dumps(result, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-image")
    parser.add_argument("--frontend-image")
    parser.add_argument("--cleanup-only", action="store_true")
    parser.add_argument("--frontend-mode", choices=("production", "development"), default="production")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    evidence = root / ".cache/frontend-security-next16" / ("real-backend" if args.frontend_mode == "production" else "real-backend-development")
    evidence.mkdir(parents=True, exist_ok=True)
    journal_path = evidence / "resources.json"
    if args.cleanup_only:
        recover_journal(journal_path, evidence)
        return
    if not args.backend_image or not args.frontend_image:
        parser.error("--backend-image and --frontend-image are required for acceptance")
    marker = "next16-" + uuid.uuid4().hex[:12]
    label = "slrms.security-test=" + marker
    password = secrets.token_urlsafe(24)
    jwt_secret = secrets.token_urlsafe(48)
    containers = []
    network = None
    frontend_process = None
    frontend_log = None
    journal = {"marker": marker, "containers": containers, "network": None}
    summary = {"tests": "NOT RUN", "fixtures_validated": False}

    def save_journal():
        write_journal(journal_path, journal)

    def docker_command(*parts):
        return docker(*parts, secret_values=(password, jwt_secret))

    write_journal(journal_path, journal, initial=True)

    def terminate(signum, frame):
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, terminate)

    def start(name, image, options, command=()):
        cid = docker_command("create", "--name", marker + "-" + name,
                     "--label", label, "--network", marker, "--network-alias", name,
                     *options, image, *command)
        containers.append(cid)
        save_journal()
        docker_command("start", cid)
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
        for port in (3000, 8000):
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", port))
        network = docker_command("network", "create", "--label", label, marker)
        journal["network"] = network
        save_journal()
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
            "JWT_SECRET_KEY": jwt_secret, "AUTH_RATE_LIMIT_ENABLED": "false",
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
        fixtures = []
        for cid in containers:
            info = json.loads(docker_command("inspect", cid))[0]
            validate_owner(info, marker)
            if not info["State"]["Running"] or any(m["Type"] == "volume" for m in info["Mounts"]):
                raise RuntimeError("Required fixture is stopped or uses a persistent volume")
            bindings = info["HostConfig"].get("PortBindings") or {}
            if any(p["HostIp"] != "127.0.0.1" for ports in bindings.values() for p in ports):
                raise RuntimeError("Fixture has a non-loopback published port")
            fixtures.append({"role": info["Name"].split(marker + "-", 1)[1], "id": cid, "image": info["Image"]})
        required = {"postgres", "redis", "minio", "backend"}
        if args.frontend_mode == "production":
            required.add("frontend")
        if {f["role"] for f in fixtures} != required:
            raise RuntimeError("Required real fixtures did not execute")
        summary["fixtures_validated"] = True
        summary["source_sha"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        (evidence / "fixtures.json").write_text(json.dumps(fixtures, indent=2), encoding="utf-8")
        test_env = dict(os.environ, APP_URL="http://localhost:3000", API_URL="http://localhost:8000",
                        SECURITY_ISOLATED_TEST="1", SECURITY_TEST_PASSWORD=password)
        npx = shutil.which("npx.cmd" if os.name == "nt" else "npx")
        with (evidence / "playwright.json").open("w", encoding="utf-8") as output:
            result = subprocess.run([npx, "playwright", "test", "--config", "playwright.real.config.js",
                                     "--reporter=json"], cwd=root / "e2e", env=test_env, stdout=output)
        report = json.loads((evidence / "playwright.json").read_text(encoding="utf-8"))
        stats = report["stats"]
        summary["stats"] = stats
        if result.returncode or stats["expected"] != 2 or stats["skipped"] or stats["unexpected"] or stats["flaky"]:
            # Raw Playwright traces/JSON may contain HTTP tokens. Upload only
            # bounded sanitized error messages and counters from this harness.
            def errors(suite):
                for spec in suite.get("specs", []):
                    for test in spec.get("tests", []):
                        for item in test.get("results", []):
                            for error in item.get("errors", []):
                                yield error.get("message", "")
                for child in suite.get("suites", []):
                    yield from errors(child)
            messages = [m for suite in report.get("suites", []) for m in errors(suite)]
            summary["errors"] = [sanitize(m, (password, jwt_secret))[:2048] for m in messages[:5]]
            raise RuntimeError("Both real-backend tests must pass without skips or flaky retries")
        summary["tests"] = "PASS"
        print("Real PostgreSQL/MinIO/backend browser acceptance: PASS")
    except BaseException as exc:
        summary["tests"] = "FAIL"
        summary["failure"] = sanitize(str(exc), (password, jwt_secret))[:2048]
        raise
    finally:
        (evidence / "result.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        if frontend_process and frontend_process.poll() is None:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(frontend_process.pid), "/T", "/F"], capture_output=True)
            else:
                os.killpg(frontend_process.pid, signal.SIGTERM)
            frontend_process.wait(timeout=15)
        if frontend_log:
            frontend_log.close()
        cleaned = cleanup_owned(marker, evidence, secret_values=(password, jwt_secret))
        cleaned["journal_archive"] = retire_journal(journal_path, marker).name
        (evidence / "cleanup.json").write_text(json.dumps(cleaned, indent=2), encoding="utf-8")
        print("Disposable resources removed:", len(cleaned["removed"]),
              "containers; networks:", len(cleaned["networks_removed"]))


if __name__ == "__main__":
    main()
