# Fix 02: cleanup operations and rollout

This runbook describes the supported S3-only deployment. **Production/staging target, IAM policy, alert delivery and infrastructure approval remain UNVERIFIED. Keep both rollout gates closed until the Owner/Ops checklist is signed.** Execute destructive/failure drills only on disposable targets. M3 does not deploy anything.

## Prerequisites and safety boundaries

- Release image includes M1, M2 and M3, and PostgreSQL is upgraded through `a7b8c9d0e1f2`. Never amend checkpoint migrations. The new status/created index supports bounded observations; the audit table preserves operator requeues in the same transaction. Plan index creation in a maintenance window for a large queue.
- An unversioned, unlocked S3-compatible target is mandatory. Enabled **or suspended** versioning is unsupported. No permanent-version purge, orphan scan, retention or undelete exists.
- Local cleanup and document DELETE rollout are **unsupported on Linux and Windows**, including plain local disks, NFS, SMB, missing roots and placeholder mounts. M3 chooses approved option B. The API gate and worker startup reject local targets before metadata deletion/claiming. Historical local intents stay durable; do not remap or mark them done. Local upload/read and low-level adapter regression remain supported; they do not certify local cleanup.
- Database and storage credentials stay in approved secret management. Only approved operators may access the operator container/DB role. There is no public requeue API. CLI execution is an OS/DB administrative capability, not an application Admin permission. Provision operator `SELECT/UPDATE` on the queue and `INSERT` on the audit table; do not grant operators locator-changing workflows.
- Separate API/backup/cleanup principals where possible. Cleanup needs the provider permissions for HeadBucket, GetBucketVersioning, GetObjectLockConfiguration and DeleteObject. Certification additionally puts/reads/deletes one UUID probe under `.slrms-certification/`. Owner must review provider-specific permission mappings and any bucket-level read capability. No script changes production bucket policies.
- Approved storage endpoint/TLS, bucket/account identity, key immutability, network isolation and least privilege must be attested by Ops. A successful SDK probe proves current behavior, not ownership approval or every future policy change.
- Use the **same explicit** `STORAGE_ENDPOINT_URL`, `STORAGE_REGION` and `STORAGE_BUCKET` for API and cleanup. Cleanup credentials may use `CLEANUP_STORAGE_ACCESS_KEY_ID` / `CLEANUP_STORAGE_SECRET_ACCESS_KEY`; fallback to API credentials must be explicitly approved, never assumed least privilege.

## Configuration defaults

| Setting | Default / meaning |
| --- | --- |
| `DOCUMENT_DELETE_ENABLED` | `false`; closed DELETE returns 503 + Retry-After |
| `DOCUMENT_MUTATIONS_ENABLED` | `true`; close for upload/retry/object mutation maintenance |
| `CLEANUP_ENABLED` | `false`; worker startup refuses to claim |
| Compose profile | `cleanup`, absent from a normal `up` |
| `CLEANUP_CERTIFICATE_FILE` | Empty in Python; Compose mounts UNVERIFIED JSON by default |
| `CLEANUP_CERTIFICATE_HOST_FILE` | Approved host certificate, mounted read-only into API/cleanup |
| `CLEANUP_CERTIFICATE_MAX_AGE_SECONDS` | 86400; range 60–604800 |
| `CLEANUP_POLL_SECONDS` / lease | 5 / 120 seconds |
| SDK connection/read timeout / total attempts | 5 / 15 seconds / 1 |
| `CLEANUP_SHUTDOWN_BUDGET_SECONDS` | 180; startup rejects insufficient budgets |
| `CLEANUP_BACKLOG_WARNING_SECONDS` | 900 seconds overdue |
| `CLEANUP_BACKLOG_CRITICAL_SECONDS` | 86400 seconds overdue; any blocked job is critical |
| Metrics cap / cache | 10000 rows per category / 30 seconds |

Environment changes require container recreation. They are not live switches. Compose `stop` is a maintenance operation; restarting a stopped service with an unchanged `true` environment reopens its application gate. Keep the independent edge gate closed throughout.

## Edge gate and mixed-version rollout

Define an operator-owned file via `DOCUMENT_DELETE_EDGE_GATE_FILE`. Initially copy the reviewed `deploy/staging/delete-maintenance.caddy` template to it. The default repository template is closed. Caddy imports it before the upstream in an explicit `route`; see [Caddy route ordering](https://caddyserver.com/docs/caddyfile/directives/route).

The edge gate rejects only `DELETE /documents/{id}` (including a trailing slash), preserving nested bookmark/rating APIs. `/metrics` is denied at the public edge. Production's direct API bind is loopback; the HTTPS overlay exposes no API host port. **Verify equivalent isolation at every real load balancer/firewall and retire every pre-M3 binary before opening the edge gate.** Old binaries cannot learn a new environment gate. An old publicly reachable instance is a rollout blocker.

Representative host commands (replace paths/project/environment with approved values):

```bash
export ENV_FILE=/secure/slrms/env.staging
export PROJECT_NAME=slrms-staging
COMPOSE=(docker compose --profile cleanup -p "$PROJECT_NAME" --env-file "$ENV_FILE" -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.staging.yml)
# Provision the reviewed CLOSED template at the configured operator-owned gate file.
cat deploy/staging/delete-maintenance.caddy > /secure/slrms/delete-gate.caddy
"${COMPOSE[@]}" exec -T caddy caddy reload --config /etc/caddy/Caddyfile
# Confirm an authenticated external document DELETE returns 503 + Retry-After.
```

For single-file bind mounts, write the existing gate file **in place** and reload only after writing completes. If using atomic file replacement, recreate Caddy so the mount points at the new inode. Check the external response after every gate change. Keep backend network access private even while proxy is closed.

## Certification and rollout order

1. Keep edge closed, `DOCUMENT_DELETE_ENABLED=false`, `CLEANUP_ENABLED=false`. Inventory and drain old API, Celery and cleanup processes; never assume lease expiry proves an old process stopped.
2. Build/review the release image and upgrade PostgreSQL with `alembic upgrade head`; run `alembic check`. Test on the intended rehearsal topology first. Do not downgrade a populated cleanup queue/audit table.
3. Obtain Owner approval of the target/account/policy. With the **cleanup principal**, certify an already existing bucket. No bucket is created or reconfigured by certification:

```bash
# Directory exists, is operator-owned and private. Output must not already exist.
"${COMPOSE[@]}" run --rm --no-deps -T --user "$(id -u):$(id -g)" \
  -v /secure/slrms/certificates:/certificates cleanup \
  python -m app.storage_certification --allow-probe --output /certificates/target-new.json
```

The CLI checks bucket accessibility, versioning/Object Lock, then PUT/GET/DELETE/HeadObject for one UUID object, confirming absence with an accessible bucket. Failure returns a sanitized error and does not certify. Investigate a failed probe before retrying; a failed compensation may leave its single probe object. Do not run a bucket-wide cleanup.

4. Grant the deployment container UID/GID read access to the certificate, keeping write access restricted to the trusted operator. The CLI creates mode 0600; a root-owned 0600 file is not automatically readable by the image's `app` user. Verify access with `run --rm --no-deps cleanup python -c 'from app.storage_certification import require_certificate; require_certificate(worker=True)'`. Read-only mounts alone do not establish trusted ownership.
5. Configure `CLEANUP_CERTIFICATE_HOST_FILE` to this approved file. The certificate binds target/region and a SHA256 of the worker access-key ID, expires, and is rechecked before every polling cycle. It is an operator-trusted capability record, not a signed provider attestation. Startup also checks real bucket policy capabilities, and each cleanup still checks M2 safety/reference guards.
6. Set `CLEANUP_ENABLED=true`; recreate/start `cleanup` using the profile. The worker has only DB/migration Compose dependencies. It has no Redis/Celery dependency, exposed port or source bind mount. Verify heartbeat health and sanitized JSON startup/outcome logs. Use `docker compose ... ps cleanup` and `logs --tail 100 cleanup`. Do not echo environment variables.
7. With the edge still closed, set `DOCUMENT_DELETE_ENABLED=true`, recreate the API, and verify read/auth/UUID behavior and a rehearsal deletion. DELETE does not demand a currently running worker; downtime leaves durable queued work.
8. After all approvals and legacy-instance checks, replace the contents of the operator edge file with a comment and reload Caddy. Observe a rehearsal lifecycle to DONE, metrics and orphan transcript behavior. Renew certification before expiry; expired/missing/mismatched files close the gate and stop further polling. Keep a tested rollback/backup plan available.

Compose's restart policy restarts exited processes; an unhealthy but still-running process is not automatically restarted by that policy alone. Ops must approve the supervisor and health escalation rather than assuming a self-healing platform exists.

## Metrics and alerts

Scrape `/metrics` privately, through the container network or an approved SSH tunnel. It has no built-in authentication, rate limiter or alert sender. It must not be internet-accessible. The existing document-status aggregation remains in the endpoint and is not bounded by the queue cap.

Cleanup gauges include all five states, per-state capped indicators, oldest unfinished age, oldest due age, overdue jobs, retry-only overdue jobs, expired leases and warning/critical booleans. Counts are exact up to the cap, then **lower bounds**, not global totals. The retry-only count shares the bounded combined due sample: when `slrms_cleanup_retry_overdue_capped=1`, it is a lower bound even if the retry count is below the cap. Ordered indexed `LIMIT cap+1` samples and indexed oldest lookups avoid unbounded queue aggregation. The cache is per API process; DB query timeout is one second per statement and failure returns 503 rather than a fabricated zero. Scrapes must allow time for several statements/cache refresh; this is not a full enterprise monitoring system.

`deploy/cleanup/prometheus-rules.yml` supplies receiver-independent rules using configured threshold gauges. Ops must add private scrape jobs, routing, recipients, escalation and a tested alert-delivery drill. **No alert delivery has been configured or verified.** Processing/expired lease counts are observations, not permission to kill/requeue a live process.

## Inspect, investigate, requeue

```bash
"${COMPOSE[@]}" run --rm --no-deps cleanup python -m app.cleanup_operator inspect JOB_UUID
# Default is dry-run and acquires/then releases the row lock without changing state.
"${COMPOSE[@]}" run --rm --no-deps cleanup python -m app.cleanup_operator requeue JOB_UUID --ticket INC-123
# Only after permissions/target/connectivity/configuration was fixed and reviewed:
"${COMPOSE[@]}" run --rm --no-deps cleanup python -m app.cleanup_operator requeue JOB_UUID --ticket INC-123 --apply
```

Inspect exposes status, attempts, retry/lease time and a sanitized error code. It omits locations, keys, credentials, lease tokens and raw messages. Only blocked/retry jobs may requeue; pending/processing/done are rejected, including expired processing jobs. Operators never edit locator fields. Attempts are retained. A `NOWAIT` row lock serializes against workers/operators; state change and audit INSERT commit together. Pre-commit failures roll back; a lost COMMIT acknowledgement can mean the change already committed. On any ambiguous command failure inspect the job and audit before retrying. The audit table records job ID, previous state, OS username, ticket and DB timestamp. OS username alone is not proof of a human identity: require per-operator access and retain platform/session audit logs.

Transient failures retry automatically with M2 backoff. For blocked jobs, inspect the constant code and fix the cause: access denied, unsupported bucket policy, locator mismatch or shared live reference. Never mark done manually or remap a stored target to make an alert disappear. Unknown or uncertified target remains blocked for Owner decision.

## Backup window and in-flight safety

1. Close edge DELETE, set application DELETE and mutation flags false, recreate/drain API instances. Verify DELETE/upload/retry receive 503 and ordinary reads still work at this stage.
2. For a consistent snapshot, drain/stop all relevant upload, processing and cleanup writers. This implementation uses a full API/frontend/Celery/cleanup maintenance stop, so reads are unavailable during the snapshot itself. Stop external schedulers/replicas too. Inventory every worker, including pre-M3/outside-Compose instances.
3. Stop cleanup claiming with graceful SIGTERM, allow active cycles to finish, and confirm processes terminated cleanly. Shutdown budget must cover bounded SDK/DB operations. An unclean/forced exit or lost DELETE response requires a storage-side fence and verified server-side request drain. **A socket timeout, lease expiry or DB disconnect does not prove a remote DELETE finished.**
4. Have Ops enforce denial of new worker DeleteObject requests (or equivalent storage fencing), check no already accepted operations remain, and record evidence. This code does not configure provider IAM or prove a production server drained. Until that evidence exists, backup is NOT VERIFIED and must remain blocked.
5. Prepare a private JSON attestation with `target_sha256` (from the approved certificate), current UTC `verified_at`, ticket, and `all_writers_stopped`, `storage_requests_drained`, `delete_fence_enforced` all true. It is trusted operator evidence, not automatic proof; validity is target-bound and 15 minutes. Never fabricate it to pass a script.
6. Run the script only in that approved window:

```bash
BACKUP_QUIESCENCE_EVIDENCE=/secure/slrms/quiescence.json \
OUTPUT_DIR=/secure-backups/slrms-new-snapshot \
  bash scripts/backup/staging-backup.sh
```

The script stops the exact Compose writers, rejects nonzero exits/unknown DB clients, dumps all PostgreSQL tables including queue/audit, then exports the unversioned bucket with streaming downloads, metadata and SHA256 manifest. MinIO needs no shell/mc. Object keys are hashed for local filenames, never used as filesystem paths. The output directory is private, must not exist and is never overwritten. Backend backup runs as the host operator UID for destination ownership. Encrypt/store backups off-host with approved access controls; hashes alone are not encryption or signatures.

Both success and failure leave writers stopped; there is **no automatic resume**. Keep gates/fence closed, validate checksums and restore drill first. Resume DB/storage, remove the provider fence only after old processes are confirmed gone, certify target/credentials, start/verify cleanup, then API/processing with DELETE still closed, then open mutations and finally edge DELETE after approval. Review durable processing leases rather than clearing them wholesale.

## Restore drill, isolated target and rollback

```bash
BACKUP_DIR=/secure-backups/slrms-approved-snapshot \
  bash scripts/restore/verify-staging-backup.sh
```

The verifier checks checksums and creates UUID verification DB/bucket targets, never overwrites existing targets and never starts cleanup. It restores the queue/audit without changing locator fields and verifies each live document key against the **restored** bucket. No S3 request to the source bucket is needed in restore/verify. Conditional PUT additionally refuses an object overwrite on a concurrent bucket-creation race. Objects larger than 5 GiB are unsupported for this restore implementation; normal SLRMS uploads are limited by the existing upload contract. Partial restores remain for investigation and cannot be blindly resumed by overwriting.

Inspect the recorded verification database privately before activation (substitute its exact UUID DB and approved DB operator):

```bash
"${COMPOSE[@]}" exec -T db psql -U APPROVED_DB_OPERATOR -d slrms_restore_verify_UUID -c \
  "SELECT status, count(*), min(next_attempt_at), count(*) FILTER (WHERE lease_expires_at <= CURRENT_TIMESTAMP) AS expired_leases FROM storage_cleanup_jobs GROUP BY status ORDER BY status"
"${COMPOSE[@]}" exec -T db psql -U APPROVED_DB_OPERATOR -d slrms_restore_verify_UUID -c \
  "SELECT id, status, attempts, next_attempt_at, lease_expires_at FROM storage_cleanup_jobs WHERE status <> 'done' ORDER BY created_at"
```

Use restore-only credentials/network policy denying all original-target access. Verify pending/processing/blocked states, lease tokens/expiry and target identity; enforce that any restored worker remains disabled. Inspect selected job IDs through the operator CLI configured for the verification DB, never by switching it to the original storage. Stored original intents must not be replayed against either the original bucket or a remapped target. A changed endpoint/bucket causes M2 target mismatch; any explicit reconciliation requires a separately reviewed Owner decision. Do not enable cleanup just because live references read successfully. Verification targets are retained, not automatically deleted. Remove only the recorded UUID test targets under a separately authorized cleanup.

Rollback means close edge and API DELETE first, freeze mutations and stop all cleanup processes with the in-flight rules above. Prefer a forward fix. Never restore a legacy DELETE binary with the route open; never drop queue/audit history or downgrade migrations with data. M3's downgrade explicitly refuses automatic audit loss; M1 also guards durable intents. Code rollback cannot recover metadata/objects already hard-deleted. A backup restore is a separate coordinated recovery, not undelete.

## Incident / acceptance checklist

- [ ] Owner confirms endpoint/account/bucket, unversioned/unlocked policy, TLS, immutability and approved principals.
- [ ] Legacy replicas and direct public backend access removed; proxy gate externally tested.
- [ ] Migrations/index/audit checked on the release candidate; queue never discarded.
- [ ] Certificate readable but not writable by application; renew/rotation process assigned.
- [ ] Rehearsal covers I01/I08/I20/I23 plus failures on the intended topology; production mount/network behavior is not inferred from unit tests.
- [ ] Metrics private, capped behavior understood, thresholds/receivers assigned; alert delivery exercised by Ops.
- [ ] Inspect/dry-run/requeue audited; worker shutdown/in-flight deletion evidence and backup fence approved.
- [ ] Isolated restore preserves all queue states and cannot reach the original target; rollback gate rehearsed.
- [ ] Supervisor restart policy, shutdown budgets, disk/certificate permissions and backup encryption verified.
- [ ] Tech Lead/Owner approve deployment. No checklist item is satisfied solely by LOCAL PASS or an operator-written JSON file.
