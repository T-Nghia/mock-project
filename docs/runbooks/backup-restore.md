# Staging backup and restore drill

These scripts support the bundled PostgreSQL and MinIO services. For managed
production services, use provider-native snapshots/PITR and versioning, but keep
the same restore-verification acceptance criteria.

## Create a backup

Run from the repository root on the staging host:

```bash
OUTPUT_DIR=/secure-backups/slrms-$(date -u +%Y%m%dT%H%M%SZ) \
  bash scripts/backup/staging-backup.sh
```

Copy the resulting directory to encrypted off-host storage. `SHA256SUMS` protects
against accidental corruption; it is not a cryptographic signature or encryption.

## Verify restoration

The verifier creates a new database and bucket and never overwrites the live
staging targets:

```bash
BACKUP_DIR=/secure-backups/slrms-20260905T120000Z \
  bash scripts/restore/verify-staging-backup.sh
```

Inspect the reported verification database and bucket. To remove automatically
after a successful future drill:

```bash
CLEANUP_VERIFY=1 BACKUP_DIR=/secure-backups/slrms-20260905T120000Z \
  bash scripts/restore/verify-staging-backup.sh
```

Record backup/restore duration, dump size, document and chunk counts, missing
objects, RPO, RTO, commit SHA, operator, and date. A backup is not accepted until
this restore verification passes.
