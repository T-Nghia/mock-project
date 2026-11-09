"""Bounded queue metrics and transactional operator recovery. No object I/O."""
from datetime import datetime
import re
import time
import threading
import uuid

from sqlalchemy import func, select, text

from app.core.config import settings
from app.models.storage_cleanup import CleanupStatus, StorageCleanupJob as Job, StorageCleanupRequeue


def inspect_job(db, job_id: uuid.UUID) -> dict:
    job = db.get(Job, job_id)
    if job is None:
        raise ValueError("job_not_found")
    # Do not print locators, requester IDs, lease tokens or raw stored messages.
    code = job.last_error_code or "none"
    if not re.fullmatch(r"[a-z_]{1,100}", code):
        code = "redacted"
    return {"job_id": str(job.id), "status": job.status.value, "attempts": job.attempts,
            "next_attempt_at": job.next_attempt_at.isoformat(),
            "lease_expires_at": job.lease_expires_at.isoformat() if job.lease_expires_at else None,
            "error_code": code}


def requeue_job(db, job_id: uuid.UUID, *, operator: str, ticket: str, apply: bool = False) -> dict:
    if not re.fullmatch(r"[\w.@\\-]{1,100}", operator) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", ticket):
        raise ValueError("invalid_audit_identity_or_ticket")
    try:
        # Serialize with claims/completion and other operators. Never steal a lease.
        job = db.scalar(select(Job).where(Job.id == job_id).with_for_update(nowait=True)
                        .execution_options(populate_existing=True))
        if job is None:
            raise ValueError("job_not_found")
        if job.status not in {CleanupStatus.BLOCKED, CleanupStatus.RETRY}:
            raise ValueError("only_blocked_or_retry_jobs_can_be_requeued")
        result = inspect_job(db, job_id) | {"dry_run": not apply}
        if apply:
            db.add(StorageCleanupRequeue(job_id=job.id, previous_status=job.status.value,
                                        operator=operator, ticket=ticket))
            job.status = CleanupStatus.PENDING
            job.next_attempt_at = func.clock_timestamp()
            job.updated_at = func.clock_timestamp()
            job.lease_token = None
            job.lease_expires_at = None
            job.completed_at = None
            job.last_error_code = "operator_requeued"
            job.last_error_message = "Operator requeue recorded in audit"
            db.commit()
        else:
            db.rollback()
        return result
    except Exception:
        db.rollback()
        raise


def queue_metrics(db) -> str:
    # Exact until capped; this is a lower bound thereafter, never a false total.
    # The status/created index bounds counts/oldest; M1 partial indexes bound due/leases.
    db.execute(text("SET LOCAL statement_timeout = '1000ms'"))
    now: datetime = db.scalar(select(func.clock_timestamp()))
    cap = settings.CLEANUP_METRICS_LIMIT
    lines = ["# TYPE slrms_cleanup_jobs gauge", "# TYPE slrms_cleanup_jobs_capped gauge"]
    oldest = 0.0
    blocked = 0
    for state in CleanupStatus:
        sample = select(Job.id).where(Job.status == state).order_by(Job.created_at).limit(cap + 1).subquery()
        count = db.scalar(select(func.count()).select_from(sample))
        lines += [f'slrms_cleanup_jobs{{status="{state.value}"}} {min(count, cap)}',
                  f'slrms_cleanup_jobs_capped{{status="{state.value}"}} {int(count > cap)}']
        if state == CleanupStatus.BLOCKED:
            blocked = count
        if state != CleanupStatus.DONE:
            created = db.scalar(select(Job.created_at).where(Job.status == state).order_by(Job.created_at).limit(1))
            if created:
                oldest = max(oldest, (now - created).total_seconds())
    due = "status IN ('pending', 'retry') AND next_attempt_at <= CURRENT_TIMESTAMP"
    expired = "status = 'processing' AND lease_expires_at <= CURRENT_TIMESTAMP"
    for name, predicate in (("overdue", due), ("expired_leases", expired)):
        if name == "overdue":
            states = list(db.scalars(text(f"SELECT status FROM storage_cleanup_jobs WHERE {predicate} ORDER BY next_attempt_at LIMIT :cap"),
                                     {"cap": cap + 1}))
            value = len(states)
            # Sample the indexed due-work prefix once. Retry-only count is a
            # lower bound too if that prefix is capped; never scan past it.
            lines += [f"slrms_cleanup_retry_overdue {states[:cap].count('retry')}",
                      f"slrms_cleanup_retry_overdue_capped {int(value > cap)}"]
        else:
            value = db.scalar(text(f"SELECT count(*) FROM (SELECT 1 FROM storage_cleanup_jobs WHERE {predicate} ORDER BY lease_expires_at LIMIT :cap) q"),
                              {"cap": cap + 1})
        lines += [f"slrms_cleanup_{name} {min(value, cap)}", f"slrms_cleanup_{name}_capped {int(value > cap)}"]
    next_due = db.scalar(text("SELECT next_attempt_at FROM storage_cleanup_jobs WHERE " + due + " ORDER BY next_attempt_at LIMIT 1"))
    late = max(0.0, (now - next_due).total_seconds()) if next_due else 0.0
    warning = settings.CLEANUP_BACKLOG_WARNING_SECONDS
    critical = settings.CLEANUP_BACKLOG_CRITICAL_SECONDS
    lines += [f"slrms_cleanup_oldest_unfinished_age_seconds {max(0.0, oldest)}",
              f"slrms_cleanup_oldest_due_age_seconds {late}",
              f"slrms_cleanup_backlog_warning_seconds {warning}",
              f"slrms_cleanup_backlog_critical_seconds {critical}",
              f"slrms_cleanup_warning {int(late >= warning)}",
              f"slrms_cleanup_critical {int(late >= critical or blocked > 0)}"]
    return "\n".join(lines) + "\n"


_cache_lock = threading.Lock()
_cached = ""
_expires = 0.0


def cached_queue_metrics(session_factory) -> str:
    global _cached, _expires
    with _cache_lock:
        if time.monotonic() >= _expires:
            with session_factory() as db:
                value = queue_metrics(db)
            _cached = value
            _expires = time.monotonic() + settings.CLEANUP_METRICS_CACHE_SECONDS
        return _cached
