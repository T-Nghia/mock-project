"""Explicit trusted certificate fixture; never used by application startup."""
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile

from app.storage_certification import target_fingerprint, principal_fingerprint


def certificate_fixture(case):
    directory = tempfile.TemporaryDirectory(prefix="cleanup-certificate-test-")
    case.addCleanup(directory.cleanup)
    path = Path(directory.name) / "target.json"
    path.write_text(json.dumps({"schema": 1, "policy": "unversioned_unlocked",
                               "target_sha256": target_fingerprint(),
                               "principal_sha256": principal_fingerprint(),
                               "certified_at": datetime.now(timezone.utc).isoformat()}), encoding="utf-8")
    return str(path)
