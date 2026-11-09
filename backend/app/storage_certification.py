"""Certify an existing S3 target with one explicitly authorized disposable probe."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import uuid

from botocore.exceptions import ClientError

from app.core.config import settings
from app.services.document_deletion_service import snapshot_storage_locator
from app.services.storage import S3Storage, StorageSafetyError


def target_fingerprint() -> str:
    if settings.STORAGE_BACKEND.lower() != "s3":
        # Supported option B: local cleanup/DELETE rollout is prohibited on both OSes.
        raise StorageSafetyError("local_cleanup_not_certified")
    target = snapshot_storage_locator("certification-probe")
    target.pop("object_key_or_location")
    target["region"] = settings.STORAGE_REGION
    return hashlib.sha256(json.dumps(target, sort_keys=True).encode()).hexdigest()


def principal_fingerprint() -> str:
    return hashlib.sha256(settings.STORAGE_ACCESS_KEY_ID.encode()).hexdigest()


def require_certificate(*, worker: bool = False) -> None:
    expected = target_fingerprint()
    try:
        with Path(settings.CLEANUP_CERTIFICATE_FILE).open(encoding="utf-8") as source:
            certificate = json.loads(source.read(8193))
        certified = datetime.fromisoformat(certificate["certified_at"])
        age = (datetime.now(timezone.utc) - certified).total_seconds()
        valid = (certificate["schema"] == 1 and certificate["policy"] == "unversioned_unlocked"
                 and certificate["target_sha256"] == expected
                 and 0 <= age <= settings.CLEANUP_CERTIFICATE_MAX_AGE_SECONDS)
        if worker:
            valid = valid and certificate["principal_sha256"] == principal_fingerprint()
        if not valid:
            raise ValueError("certificate mismatch or expiry")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise StorageSafetyError("target_uncertified") from exc


def require_worker_enabled() -> None:
    if not settings.CLEANUP_ENABLED:
        raise StorageSafetyError("cleanup_disabled")
    require_certificate(worker=True)


def certify_target() -> dict:
    target = target_fingerprint()
    storage = S3Storage(cleanup=True)
    key = ".slrms-certification/" + uuid.uuid4().hex
    payload = b"SLRMS cleanup capability probe"
    created = False
    try:
        storage.validate_cleanup_target()
        storage.save(key, payload, "application/octet-stream")
        created = True
        if storage.read(key) != payload:
            raise StorageSafetyError("certification_read_mismatch")
        storage.delete(key)
        created = False
        try:
            storage.client.head_object(Bucket=storage.bucket, Key=key)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") not in {"404", "NoSuchKey"}:
                raise
            storage.client.head_bucket(Bucket=storage.bucket)
        else:
            raise StorageSafetyError("certification_delete_unconfirmed")
        return {"schema": 1, "policy": "unversioned_unlocked", "target_sha256": target,
                "principal_sha256": principal_fingerprint(), "certified_at": datetime.now(timezone.utc).isoformat()}
    finally:
        try:
            if created:
                storage.delete(key)
        finally:
            storage.client.close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-probe", action="store_true")
    args = parser.parse_args(argv)
    if not args.allow_probe:
        parser.error("--allow-probe is required; the existing bucket will receive one temporary object")
    try:
        if args.output.exists():
            raise FileExistsError("Refusing to overwrite an existing certificate")
        certificate = certify_target()
        # Trusted operator provisioned file. Never auto-learn a target at worker startup.
        with args.output.open("x", encoding="utf-8") as target:
            target.write(json.dumps(certificate, sort_keys=True) + "\n")
        args.output.chmod(0o600)
        print(json.dumps({"event": "storage_target_certified", "target_sha256": certificate["target_sha256"]}))
        return 0
    except Exception as exc:
        print(json.dumps({"error": "target_certification_failed", "error_type": type(exc).__name__}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
