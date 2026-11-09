# Staging backup and restore drill

Fix 02 supersedes the old live dump-then-copy workflow. Follow the prerequisites,
storage fencing/in-flight drain and resume order in
[storage cleanup operations](storage-cleanup-operations.md). These scripts support
bundled PostgreSQL and unversioned, unlocked S3-compatible storage. Managed
snapshots require a separately approved consistent-window procedure. Versioned
object purge and automatic production recovery are unsupported.

## Create a backup

Run only in an approved maintenance window, with all writers stopped and verified
target-bound Ops evidence. The script rejects unknown DB clients/unclean stops and
leaves services stopped after success or failure:

```bash
BACKUP_QUIESCENCE_EVIDENCE=/secure/slrms/quiescence.json \
OUTPUT_DIR=/secure-backups/slrms-$(date -u +%Y%m%dT%H%M%SZ) \
  bash scripts/backup/staging-backup.sh
```

Copy the resulting directory to encrypted off-host storage. `SHA256SUMS` protects
against accidental corruption; it is not a cryptographic signature or encryption.

## Verify restoration

The verifier creates UUID database and bucket targets and never overwrites live
targets. Cleanup stays disabled; queue locators are not remapped. Use credentials
and network controls that deny access to the original target during restore:

```bash
BACKUP_DIR=/secure-backups/slrms-20260905T120000Z \
  bash scripts/restore/verify-staging-backup.sh
```

Inspect pending/processing/blocked jobs, leases, live references and the reported
targets. They remain for investigation; there is no automatic deletion or resume.
Remove only recorded disposable verification targets under separate authorization.

Record backup/restore duration, dump size, document and chunk counts, missing
objects, RPO, RTO, commit SHA, operator, and date. A backup is not accepted until
this restore verification and the full operational checklist pass. Lease expiry
is not proof that old storage requests stopped. Code rollback cannot restore an
already hard-deleted object or document. Never drop a populated cleanup queue or
reopen a legacy DELETE route during rollback.
