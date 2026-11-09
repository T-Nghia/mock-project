"""Independent worker heartbeat; intentionally never queries Redis/Celery."""
from pathlib import Path
import time

from app.core.config import settings


def healthy() -> bool:
    try:
        age = time.time() - Path(settings.CLEANUP_HEARTBEAT_FILE).stat().st_mtime
        # Windows filesystem timestamps can lead the sampled wall clock by a
        # small tick. Tolerate that jitter, not a substantially future heartbeat.
        return bool(settings.CLEANUP_HEARTBEAT_FILE) and -5 <= age <= settings.CLEANUP_LEASE_SECONDS + 2 * settings.CLEANUP_POLL_SECONDS + 15
    except OSError:
        return False


if __name__ == "__main__":
    raise SystemExit(0 if healthy() else 1)
