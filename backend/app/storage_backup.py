"""Read-only S3 backup and fresh-bucket restore; never remap cleanup intents."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import uuid

from botocore.exceptions import ClientError
from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.document import Document
from app.services.storage import S3Storage, StorageSafetyError
from app.storage_certification import target_fingerprint


def require_paused() -> None:
    if settings.DOCUMENT_DELETE_ENABLED or settings.DOCUMENT_MUTATIONS_ENABLED or settings.CLEANUP_ENABLED:
        raise StorageSafetyError("backup_requires_closed_gates")
    target_fingerprint()


def validate_quiescence(path: Path) -> dict:
    with path.open(encoding="utf-8") as source:
        evidence = json.loads(source.read(8193))
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(evidence["verified_at"])).total_seconds()
    if (evidence.get("target_sha256") != target_fingerprint() or not 0 <= age <= 900
            or any(evidence.get(field) is not True for field in (
                "all_writers_stopped", "storage_requests_drained", "delete_fence_enforced"))
            or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", evidence.get("ticket", ""))):
        raise StorageSafetyError("quiescence_unverified")
    return evidence


def export_objects(directory: Path, *, revision: str, evidence_file: Path) -> dict:
    require_paused()
    evidence = validate_quiescence(evidence_file)
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("full_commit_revision_required")
    directory.mkdir(parents=False, exist_ok=False)
    storage = S3Storage(cleanup=True)
    objects = []
    try:
        storage.validate_cleanup_target()
        for page in storage.client.get_paginator("list_objects_v2").paginate(Bucket=storage.bucket):
            for item in page.get("Contents", []):
                key = item["Key"]
                filename = hashlib.sha256(key.encode()).hexdigest() + ".object"
                destination = directory / filename
                metadata = storage.client.head_object(Bucket=storage.bucket, Key=key)
                storage.client.download_file(storage.bucket, key, str(destination))
                with destination.open("rb") as source:
                    digest = hashlib.file_digest(source, "sha256").hexdigest()
                objects.append({"key": key, "file": filename, "sha256": digest,
                                "size": destination.stat().st_size,
                                "content_type": metadata.get("ContentType", "application/octet-stream"),
                                "metadata": metadata.get("Metadata", {})})
        manifest = {"schema": 1, "created_at": datetime.now(timezone.utc).isoformat(),
                    "revision": revision, "target_sha256": target_fingerprint(),
                    "source_bucket": storage.bucket, "policy": "unversioned_unlocked",
                    "quiescence": evidence, "objects": objects}
        (directory / "manifest.json").write_text(json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8")
        return {"objects": len(objects), "target_sha256": manifest["target_sha256"]}
    finally:
        storage.client.close()


def checked_manifest(directory: Path) -> dict:
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != 1 or manifest.get("policy") != "unversioned_unlocked":
        raise StorageSafetyError("invalid_backup_manifest")
    keys = set()
    for item in manifest["objects"]:
        filename = hashlib.sha256(item["key"].encode()).hexdigest() + ".object"
        if filename != item["file"] or item["key"] in keys:
            raise StorageSafetyError("invalid_backup_entry")
        keys.add(item["key"])
        path = directory / filename
        if path.is_symlink() or path.stat().st_size != item["size"]:
            raise StorageSafetyError("backup_checksum_mismatch")
        with path.open("rb") as source:
            if hashlib.file_digest(source, "sha256").hexdigest() != item["sha256"]:
                raise StorageSafetyError("backup_checksum_mismatch")
    return manifest


def restore_objects(directory: Path, bucket: str) -> dict:
    require_paused()
    if not re.fullmatch(r"slrms-restore-verify-[0-9a-f]{32}", bucket):
        raise StorageSafetyError("restore_requires_fresh_generated_target")
    manifest = checked_manifest(directory)
    if bucket == manifest["source_bucket"]:
        raise StorageSafetyError("restore_requires_separate_target")
    storage = S3Storage(cleanup=True)
    try:
        try:
            storage.client.head_bucket(Bucket=bucket)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") not in {"404", "NoSuchBucket"}:
                raise
        else:
            raise StorageSafetyError("restore_target_already_exists")
        arguments = {} if settings.STORAGE_REGION == "us-east-1" else {
            "CreateBucketConfiguration": {"LocationConstraint": settings.STORAGE_REGION}}
        storage.client.create_bucket(Bucket=bucket, **arguments)
        for item in manifest["objects"]:
            # Even a concurrent creator of this UUID bucket must not cause an
            # overwrite. Supported SLRMS objects fit within one conditional PUT.
            if item["size"] > 5 * 1024**3:
                raise StorageSafetyError("restore_object_exceeds_supported_size")
            with (directory / item["file"]).open("rb") as source:
                storage.client.put_object(Bucket=bucket, Key=item["key"], Body=source, IfNoneMatch="*",
                                          ContentType=item["content_type"], Metadata=item["metadata"])
        return {"objects": len(manifest["objects"]), "restored_bucket": bucket}
    finally:
        storage.client.close()


def verify_live_references(session_factory=SessionLocal) -> dict:
    require_paused()
    storage = S3Storage(cleanup=True)
    count = 0
    try:
        storage.validate_cleanup_target()
        last_id: uuid.UUID | None = None
        while True:
            # The isolated restore stays immutable. Read scalar pages and close
            # their transactions before network I/O, as in the M2 worker.
            with session_factory() as db:
                query = select(Document.id, Document.file_path).order_by(Document.id).limit(1000)
                if last_id is not None:
                    query = query.where(Document.id > last_id)
                rows = db.execute(query).all()
            if not rows:
                break
            for _, key in rows:
                storage.client.head_object(Bucket=storage.bucket, Key=key)
                count += 1
            last_id = rows[-1][0]
        return {"verified_live_documents": count, "cleanup_enabled": False}
    finally:
        storage.client.close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["export", "restore", "verify"])
    parser.add_argument("--directory", type=Path)
    parser.add_argument("--revision")
    parser.add_argument("--quiescence-evidence", type=Path)
    parser.add_argument("--bucket")
    args = parser.parse_args(argv)
    try:
        if args.operation == "export":
            result = export_objects(args.directory, revision=args.revision, evidence_file=args.quiescence_evidence)
        elif args.operation == "restore":
            result = restore_objects(args.directory, args.bucket or "slrms-restore-verify-" + uuid.uuid4().hex)
        else:
            result = verify_live_references()
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"error": "storage_backup_failed", "error_type": type(exc).__name__}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
