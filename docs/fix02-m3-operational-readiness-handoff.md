# Fix 02 / M3 — operational readiness handoff

Local implementation for Tech Lead and Gemini. **Not a production-readiness approval.** Production target/IAM/network controls, real-topology rehearsal, alert recipients/delivery and deployment remain UNVERIFIED/BLOCKED. No stage, commit, push, PR, merge or deployment is authorized/performed in M3.

## A. Git state

- Branch: `fix/storage-reliability-cleanup`.
- Unchanged M2 base/HEAD: `26050faee3486fd2d9c93d6df163c4e1e4bb5694`.
- Parent: approved M1 `ac8cbf7333571e7c89ffd23a57d1024aedd5e8c7`.
- Working tree was clean; M1/M2 checkpoints were not amended, reset or rebased. Changes remain unstaged. No Python/npm application dependency, authentication implementation, RAG algorithm, retention, undelete or version-purge feature was introduced. CI uses the existing deployment's Caddy version as a checksum-pinned test tool.
- Full tracked + untracked patch/audit: `.cache/fix02-m3/m3-review.patch` and `.cache/fix02-m3/git-audit.json`. Runtime/log/cache/build artifacts and secrets are excluded. Audit verifies normalized Git blobs, whitespace, empty index and patch application to a disposable copy of M2.

## B. Files modified/added

Modified (19):

```text
.github/workflows/ci.yml
backend/app/cleanup_worker.py
backend/app/core/config.py
backend/app/main.py
backend/app/models/storage_cleanup.py
backend/app/services/storage_cleanup_service.py
backend/tests/integration/reliability_support.py
backend/tests/integration/s3_fault_proxy.py
backend/tests/integration/test_cleanup_independence.py
backend/tests/integration/test_document_deletion.py
backend/tests/test_documents.py
deploy/staging/Caddyfile
docker-compose.prod.yml
docker-compose.staging.yml
docker-compose.yml
docs/runbooks/backup-restore.md
docs/runbooks/worker-recovery.md
scripts/backup/staging-backup.sh
scripts/restore/verify-staging-backup.sh
```

Added (21):

```text
backend/alembic/versions/a7b8c9d0e1f2_cleanup_operations.py
backend/app/cleanup_health.py
backend/app/cleanup_operator.py
backend/app/core/maintenance.py
backend/app/services/cleanup_operations.py
backend/app/storage_backup.py
backend/app/storage_certification.py
backend/tests/cleanup_fixture.py
backend/tests/integration/operational_server.py
backend/tests/integration/test_cleanup_operations.py
backend/tests/integration/test_cleanup_proxy.py
backend/tests/integration/test_cleanup_rollout.py
backend/tests/integration/test_storage_backup.py
backend/tests/test_cleanup_rollout.py
deploy/cleanup/prometheus-rules.yml
deploy/cleanup/unverified.json
deploy/staging/delete-maintenance.caddy
docs/fix02-m3-operational-readiness-handoff.md
docs/runbooks/storage-cleanup-operations.md
e2e/tests/storage-operational.spec.js
scripts/test/operational_acceptance.py
```

## C. Metrics, logs and operator recovery (M3-T1)

Queue gauges report every state, oldest unfinished/due ages, overdue work, retry-only overdue work, expired leases and configured warning/critical conditions. Defaults are 900/86400 seconds overdue; any blocked job is critical. Counts are exact until the configured cap, then lower bounds with explicit capped gauges. Retry-overdue is derived from the bounded combined due prefix; if that prefix is capped, its retry-only value is a lower bound even below the configured cap. Per-process caching and one-second-per-statement DB timeout bound scrape work. The new `(status, created_at)` index supports ordered capped per-state/oldest lookups; existing M1 partial indexes support ordered due/expired queries. This is an additive migration, not a queue architecture change. No unbounded queue `GROUP BY count(*)` was added.

`/metrics` has no application authentication or alert delivery and must be scraped privately. The Caddy public edge denies it; direct production API bind is loopback. The legacy document-status aggregation in this endpoint remains unbounded. Queue gauges are not exact global counts after saturation and cache is not shared between API instances. No outcome counter is invented from process-local state.

Inspect omits locators, keys, lease token and raw stored messages. Requeue defaults dry-run, rejects non-blocked/non-retry states, preserves attempts/locator and uses NOWAIT row locking with `populate_existing` to refresh cached ORM state. A real PostgreSQL regression first reproduced a stale RETRY object bypassing a newly committed PROCESSING lease; the final code rejects it with the lease and audit unchanged. Requeue and its audit INSERT commit atomically; pre-commit rollback leaves both unchanged. CLI accepts no target-changing arguments and exposes no public API. OS/DB authorization and per-operator platform audit remain prerequisites; recorded OS username is not cryptographic human identity.

Worker lifecycle/failure/outcome events now use sanitized JSON messages. No raw exception text, SDK URLs, credentials or document content is included. Settings validation also hides input values in rendered errors: a fake-secret regression reproduced the old input dictionary exposure before this formatting-only fix. Authentication/validation policy is unchanged. Prometheus rules are examples only: receiver/routing/delivery and operational log collection are not configured by this milestone.

## D. Deployment and maintenance gate (M3-T2)

Compose `cleanup` is a backend-image service with `python -m app.cleanup_worker`, restart supervision, 180-second default graceful shutdown budget, tmpfs heartbeat and healthcheck. Only DB/migration are service dependencies. No Redis/Celery dependency, public port, existing storage mount or source bind is added to the production cleanup service. The profile is opt-in, `CLEANUP_ENABLED=false`, and the default mounted target record is UNVERIFIED.

`DOCUMENT_DELETE_ENABLED=false` returns 503 with Retry-After before document/job mutation. A second flag closes document mutations for backup. Read APIs remain available under the normal DELETE maintenance gate. DELETE does not require a live cleanup worker: durable queue semantics remain intact. The middleware also covers a legacy route in the same ASGI application. A default-closed Caddy gate protects pre-M3 replicas at the ingress; old externally reachable binaries remain a mandatory infrastructure blocker until retired. Configuration uses explicit route ordering per [Caddy documentation](https://caddyserver.com/docs/caddyfile/directives/route).

Initial regression caught middleware intercepting nested bookmark/rating DELETE and Compose retaining the base public port when adding a loopback port. Both were fixed: match only the document DELETE path and use `!override` for the production port list. Nested social APIs pass regression. Existing M1 local unit API tests explicitly isolate the deployment guard to retain transaction/RBAC assertions; real M3 gate tests exercise the unmocked middleware with PG/S3 and a real Caddy proxy.

## E. S3 certification and local mount safety (M3-T3)

Approved option **B** is implemented: local cleanup and DELETE rollout are prohibited on Linux and Windows. No `is_dir`, sentinel or `st_dev` claim is used as proof. An actual backing-root rename plus empty placeholder test verifies API rejection, worker startup refusal, pending job/zero attempts/no completion and retained bytes. Low-level M2 adapter tests remain useful but do not certify a supported local deployment. NFS/SMB/network mounts are unsupported; no real production unmount was performed.

S3 certification checks an already-existing bucket, versioning and Object Lock, and one explicitly authorized UUID PUT/GET/DELETE/HEAD probe. It creates no bucket and changes no bucket policy. The read-only trusted certificate binds endpoint/bucket/backend/region plus the worker access-key-ID hash, expires by default after 24 hours and is rechecked before polling. API requires target certification; worker additionally requires the certified principal and actual startup capability checks. M2 still validates bucket policy/locator/live references for each job.

A certificate is an operator-trusted capability record, not provider ownership approval or a signed policy guarantee. Production account/bucket/IAM/TLS/certificate filesystem permissions are UNVERIFIED. Missing/expired/mismatched certificate, local backend or disabled cleanup fails closed. No automatic startup learning, version deletion or target remapping exists.

## F. Backup, restore and rollback safeguards (M3-T4)

The old live dump-then-mirror path is replaced. Scripts require an approved window and target-bound, fresh Ops evidence of all writers stopped, requests drained and storage delete fencing. They stop exact Compose writers, reject unclean exits/unknown DB clients, dump all tables (including queue/audit) and export S3 bytes/metadata with SHA256 manifest. MinIO does not need shell/mc. Both failure and success leave writers stopped; there is no automatic resume.

The evidence JSON is an attestation, **not an automated proof of production IAM/server-side drain**. A timeout, lost acknowledgement, expired lease or disconnected process is insufficient. Production backup consistency remains BLOCKED until Ops enforces the fence/in-flight checks. Controlled tests use a real MinIO server plus an HTTP fault-injection fence; no production policy is altered.

Restore uses fresh UUID database/bucket targets, validates hashes first, refuses existing targets/object overwrites and retains partial results. It never rewrites queue locators or starts cleanup. The PostgreSQL drill preserves pending/processing/blocked jobs and lease metadata; restore/verify has a proxy fence rejecting the source bucket and asserts **zero attempted source-bucket requests**. Restored live documents are verified only against the restored bucket. Restore-only credentials/network policy must enforce the equivalent prohibition in rehearsal/production. Fixture teardown removes only owned disposable resources outside the restore/verify phase.

M3 migration downgrade refuses audit loss; M1's queue downgrade guard remains. Rollback closes ingress/API gates first, stops/drains workers and keeps durable intent; prefer a forward fix. A code rollback is not undelete. No claim is made that a full production Compose backup window or real provider IAM fence was exercised locally.

## G. Full acceptance traceability I01–I24 (M3-T5)

P = real PostgreSQL; S = real MinIO; R/C = real Redis/Celery prefork; F = controlled failure/barrier/proxy injection; B = real browser and HTTP backend; E = real Caddy edge. Files below are relative to `backend/tests/integration` unless `unit/` (`backend/tests`) or `browser/` (`e2e/tests`) is indicated. All results refer to local candidate source based on M2; remote CI and exact committed release-candidate evidence require a later approved commit/push. IDs follow Astra's original matrix supplied by Tech Lead, including the eight clarified IDs.

| Scenario ID | Test File/Method | Infrastructure | Assertions | Actual Result | Evidence | Remaining Gate |
| --- | --- | --- | --- | --- | --- | --- |
| I01 | `test_cleanup_rollout.test_real_api_delete_queues_while_worker_disabled_then_cleans_when_enabled`; `test_document_deletion.test_hard_delete_preserves_chat_snapshots_and_cascades_document_dependents`; `browser/storage-operational.spec.js` | P,S,B | 204 only after commit; one pending intent; FK effects; real deletion/DONE | LOCAL PASS | PG/MinIO suites + real browser/queue check | REHEARSAL REQUIRED on intended topology |
| I02 | `test_cleanup_rollout.test_api_auth_uuid_and_ownership_still_enforced_with_open_gate` | P,S | 401 missing token; 403 student/non-owner teacher; no queue/object mutation | LOCAL PASS | Real authenticated API + retained S3 bytes | PR evidence on release-candidate SHA; REMOTE NOT RUN |
| I03 | `test_document_deletion.test_authentication_autobegin_and_api_error_contract`; rollout auth/UUID test | P | Invalid UUID 422; valid missing ID 404; no extra intent | LOCAL PASS | PG API tests | Release-candidate PR evidence |
| I04 | `test_storage_reliability.test_I04_http_503_is_retry_then_actual_minio_recovery`, `test_I04_real_read_timeout_is_retry_then_recovery` | P,S,F | Retry durable; same object later deleted and DONE | LOCAL PASS | Linux acceptance | Rehearsal target timeout configuration |
| I05 | `test_cleanup_postgresql.test_I05_I06_api_process_crashes_preserve_transaction_boundary` | P,F | API process hard-exits after actual commit; durable intent survives | LOCAL PASS | Linux/Windows process/PG evidence | Real-topology rehearsal |
| I06 | Same API crash test; M1 rollback tests | P,F | Before-commit exit rolls back document and queue changes | LOCAL PASS | PG process evidence | Release-candidate PR evidence |
| I07 | Rollout real API normal-delete test; first browser lifecycle test | P,S,B | First 204, repeat 404; one job and retained/unmodified effects on repeat | LOCAL PASS | Browser and PG/S3 queue assertions | Release-candidate PR evidence |
| I08 | `test_document_deletion.test_postgresql_row_lock_serializes_concurrent_deletes`; second browser test | P,S,B | Concurrent HTTP DELETEs return 204/404; one durable intent; no stale ORM error | LOCAL PASS | PG lock evidence + real HTTP Promise.all + two total E2E jobs | REHEARSAL REQUIRED |
| I09 | `test_cleanup_rollout.test_I09_database_insert_or_delete_failure_preserves_real_storage`; M1 trigger rollback methods | P,S,F | Real INSERT/DELETE trigger failures yield 500, metadata retained, zero committed jobs, original S3 bytes retained | LOCAL PASS | Real trigger/PG/S3 tests | Release-candidate PR evidence |
| I10 | `test_cleanup_postgresql.test_I10_delete_during_embedding_stops_writes_and_failure_handler_after_delete` | P,F | Processing notices deletion, no chunks/FAILED resurrection | LOCAL PASS | Real PG barrier | Rehearsal processing workload |
| I11 | `test_cleanup_postgresql.test_I11_chunk_insert_holds_document_lock_and_delete_cascades_committed_chunks` | P,F | Actual chunk INSERT lock; DELETE waits/cascades; later writes rejected | LOCAL PASS | pg_stat_activity and row locks | Release-candidate PR evidence |
| I12 | `test_cleanup_postgresql.test_I12_crash_before_and_after_claim_commit_is_recoverable` | P,F | Uncommitted claim rolls back; committed lease recovers after DB expiry | LOCAL PASS | Actual subprocess exits | Supervision rehearsal |
| I13 | `test_storage_reliability.test_I13_delete_succeeded_but_connection_lost_replays_idempotently` | P,S,F | Object removed, response lost; retry replay completes idempotently | LOCAL PASS | Real S3 + dropped TCP response | Provider request-drain semantics remain UNVERIFIED |
| I14 | `test_storage_reliability.test_I14_process_crash_after_real_delete_before_done_is_recovered` | P,S,F | Durable processing intent survives; expired-lease replay DONE | LOCAL PASS | Real object effect/process exit | Rehearsal |
| I15 | Cleanup PG two-worker/skip-locked/token tests and `test_I15_expired_and_wrong_tokens_cannot_complete_or_overwrite_new_worker` | P,F | One claim; token/clock fencing; stale completion rejected | LOCAL PASS | Real concurrent sessions/locks | Multi-instance rehearsal |
| I16 | `test_celery_redelivery.test_I16_actual_prefork_child_loss_redelivers_after_delete_without_writes` | P,R/C,F | Verified child SIGKILL; actual redelivery; document_deleted/no new chunks | LOCAL PASS | Linux prefork, not eager mode | Deployment broker/worker rehearsal |
| I17 | `test_cleanup_independence.test_I17_independent_entrypoint_cleans_object_with_redis_and_celery_down` | P,S,F | Broker stopped; separate cleanup process deletes/DONE and shuts down | LOCAL PASS | Separate broker-down run | Intended production supervision |
| I18 | `test_cleanup_postgresql.test_I18_real_connection_loss_during_completion_keeps_recoverable_lease` | P,F | Owned connection terminated; durable lease retained; recoverable completion | LOCAL PASS | Real pg_terminate_backend on owned connection | DB failover rehearsal |
| I19 | Real access-denied/missing-bucket tests in `test_storage_reliability`; rollout certificate tests | P,S | Access/invalid target blocked, never missing-object success; uncertified startup closed | LOCAL PASS | Real S3 auth/bucket rejection + cert tests | Approved IAM/target: BLOCKED |
| I20 | M1 orphan/ownership/provider-concurrency/FK tests; first browser test | P,S,B,F | KEEP CHAT, snapshots, null document_id, owner get/delete/repeat, orphan post 409, others 404, no late answer/FK500, correct tags/FKs | LOCAL PASS | Real PG tests + retained real-backend browser citations | REHEARSAL REQUIRED; no B03 policy change |
| I21 | `test_local_reliability` and LocalDeletionContract/Windows handle tests; M3 local replacement rollout test | P,F | Missing root retries in adapter evidence; EIO retry/permission blocked; M3 local entrypoint cannot claim/DONE on placeholder | LOCAL PASS | Real Linux/Windows filesystem, injected EIO; actual root rename | Local cleanup UNSUPPORTED/BLOCKED, including NFS/SMB |
| I22 | Real versioned/locator-mismatch tests; `test_cleanup_rollout.test_versioned_target_cannot_be_certified` | P,S | No purge/delete marker; mismatch never remapped; versioned target cannot certify | LOCAL PASS | Real versioned bucket + Object Lock unit failures | Production policy UNVERIFIED |
| I23 | `test_storage_backup.test_I23_real_pg_dump_restore_preserves_queue_and_never_remaps_target`; storage snapshot/fence/corruption tests; unit shutdown/drain tests; M1 `test_migration_downgrade_refuses_to_discard_unfinished_cleanup_intent` | P,S,F | Consistent disposable snapshot; real dump/restore; live references and pending/processing/blocked/leases retained; disabled worker; zero source-bucket restore requests; no remap/queue loss | LOCAL PASS for component drill | Real pg_dump/pg_restore, real copied bytes/metadata, controlled fence | REHEARSAL REQUIRED; complete deployment window/provider fencing NOT VERIFIED/BLOCKED |
| I24 | `test_storage_reliability.test_I24_live_shared_object_blocks_physical_s3_delete`; cleanup PG reference test | P,S | Live shared key blocks cleanup and remains readable | LOCAL PASS | Real S3 object + PG reference | Preserve immutable-key upload policy |

M1 orchestration unit cases still use SQLite/spies in their original scope; they are not used as PostgreSQL/locking/S3 evidence in this matrix. LLM/embedding providers are deterministic test doubles with a real backend and real PG retrieval, not external AI calls. Controlled proxy failures are not a claim of a physical disk/network mount/provider IAM failure.

## H. Local validation and regression

Final evidence is retained locally under ignored `.cache/fix02-m3`. Required test groups explicitly reject zero collection/unexpected skips; platform-specific modes are executed separately.

| Check | Actual local result | Evidence |
| --- | --- | --- |
| Full Windows backend discovery with PG/S3/Caddy enabled | 332 tests: 324 PASS, 8 expected platform/broker-mode skips | `backend-final.log` |
| Operational CI group | 35 PASS, zero skips | `ci-operations-final.log` |
| Linux PG/S3/prefork/local/operations acceptance | 80 PASS, zero skips | `linux-final.log` |
| Redis/Celery-down independent entrypoint | 1 PASS, zero skips; graceful SIGTERM; correct JSON outcome/job/lease | `broker-final.log` |
| Native Caddy proxy | Linux 1 PASS and Windows 1 PASS, real legacy handler blocked | `linux-proxy-final.log`, operational suite |
| Real-backend production browser | 2 PASS, zero skips/flakes/unexpected outcomes; two DONE jobs, zero remaining objects | `browser-final.log` |
| Backend coverage threshold 70% | PASS, 86.59% (3364/3885 statements; displayed 87%) | `coverage-final.json` |
| Ruff | PASS for `app tests alembic ../scripts/test` | Tool output |
| Mypy | 23 CI critical paths Linux PASS; main separately PASS with silent imports; 9 worker/operations Windows paths PASS | Tool output |
| Frontend lint/typecheck | PASS | Actual npm commands |
| Frontend production build | PASS in real-backend browser runner | `acceptance/frontend-build.log` |
| Browser discovery | 195 tests in 14 files | `browser-discovery.log` |
| Migrations | Fresh PG upgrade through M3, Alembic check/current PASS | Actual migration output |
| Compose/bash/actionlint | Merged production/staging, scripts on Linux bash, actionlint 1.7.12 PASS | `deployment-verified.log` |
| Alert example/default target syntax | YAML parses as four rules; JSON status UNVERIFIED | Existing js-yaml/JSON parser; no promtool or delivery test |

The eight skips are five POSIX integration cases, one POSIX symlink adapter case, one Linux-prefork case and the deliberately broker-down mode. They run in the zero-skip Linux/broker groups. The unknown-ACK case now additionally executes real PostgreSQL COMMIT and injects a controlled acknowledgement exception: HTTP 500, committed intent/document deletion retained, original real S3 bytes unchanged until worker recovery. This is application-level fault injection after a real commit, not a claim of intercepting a physical PostgreSQL COMMIT packet. Operator rollback testing flushes real queue/audit writes before injecting the pre-commit failure.

Commands use the existing root `.venv` and a local ignored harness that provisions only new labeled PG/MinIO/Redis containers, loopback ports and tmpfs, without existing volumes. New source adds no production dependency. Representative commands:

```text
python .cache/fix02-m3/run.py up
python .cache/fix02-m3/run.py run -m alembic upgrade head
python .cache/fix02-m3/run.py run -m alembic check
python .cache/fix02-m3/run.py run-defaults -m coverage run --data-file=../.cache/fix02-m3/.coverage --source=app -m unittest discover -s tests -p test_*.py -v
python .cache/fix02-m3/run.py run-linux -m unittest tests.integration.test_cleanup_postgresql tests.integration.test_storage_s3 tests.integration.test_storage_reliability tests.integration.test_celery_redelivery tests.integration.test_local_reliability tests.test_storage_cleanup.LocalDeletionContractTestCase tests.integration.test_cleanup_operations tests.integration.test_cleanup_rollout tests.integration.test_storage_backup.StorageBackupTestCase tests.test_cleanup_rollout -v
# Dedicated Redis stopped/restored in finally; RUN_BROKER_DOWN_INTEGRATION=1:
python .cache/fix02-m3/run.py run-linux -m unittest tests.integration.test_cleanup_independence -v
# RUN_OPERATIONAL_E2E=1, ENV=test, dedicated PG/S3 settings, optional local Node/Edge paths:
python scripts/test/operational_acceptance.py
python -m ruff check app tests alembic ../scripts/test
python -m mypy <23 CI production-critical paths> --ignore-missing-imports --check-untyped-defs --explicit-package-bases --platform linux
python -m mypy app/main.py --ignore-missing-imports --check-untyped-defs --explicit-package-bases --follow-imports=silent
python .cache/fix02-m3/run.py down
```

The harness is a local ignored convenience; reviewers outside this workspace can reproduce the source-controlled CI service setup/commands with dedicated disposable resources instead. The final 36 source/test/config blobs were pinned before full regression and verified unchanged afterward; only handoff/runbook text was finalized later. All three labeled fixture containers/network were removed after ID/label/name/no-volume checks. Existing SLRMS containers remained stopped; their images/volumes were untouched. Owned API/Next/cleanup/browser/proxy processes stopped and generated untracked TypeScript build info was removed. Git index remains empty.

Frontend lint/typecheck passed; the browser runner builds/serves the actual Next production bundle with its disposable backend URL. The first dev-server browser attempt encountered existing StrictMode refresh-cookie effect replay; production mode passes. Authentication source was not changed. An expanded mypy invocation including `app/main.py` with unrestricted import traversal exposed nine pre-existing errors in unchanged auth/folder/social modules; the maintained CI critical-path check plus separately checked main passes. This is a disclosed typechecking boundary, not a claim of a clean whole-repository mypy run.

Initial full runs caught the nested-route gate issue, the expected migration head assertion and Windows sub-tick future heartbeat jitter. Assertions were retained, migration expectation follows the new additive revision, and heartbeat tolerates only five seconds of wall-clock jitter while stale/substantially future values fail. The separate broker test's old key/value log assertion was replaced by stricter JSON assertions for exact job ID, DONE, accepted lease and clean shutdown. Cached-row requeue and Settings-input redaction regressions were reproduced red before the minimal fixes, then passed in the full/required groups. A sandbox-only unit invocation failed because Temp writes were denied, then passed outside the sandbox without changing assertions. A later browser login 500 was traced to the ignored fixture harness retaining an old dynamic Redis host port after restart; the harness now refreshes only verified fixture mappings and the unchanged authentication assertions pass.

## I. CI readiness

Existing PostgreSQL/Redis services, pinned loopback Chainguard MinIO, lint/mypy/migration/coverage/frontend checks and no-skip reliability/broker-down guards remain. Operational recovery requires at least 35 collected tests, no skips, real Docker PG dump/restore and real Caddy. Browser acceptance installs existing frontend/E2E dependencies and requires exactly two expected, zero skipped/unexpected browser tests plus actual DONE/empty-bucket assertions. Test-only providers are excluded from the production backend image by the existing Docker ignore.

Merged production/staging Compose, Linux bash syntax and actionlint 1.7.12 passed locally. Actionlint caught an invalid job-level services context and it was moved into the operational step. A real render also showed that inactive profiles are omitted: CI explicitly selects cleanup only for config inspection/build, while default runtime remains inactive. Caddy Docker Hub layer downloads failed with anonymous CDN EOF twice locally. CI therefore uses **same-version 2.10.2** from the official release with immutable archive SHA256 `5c218bc34c9197369263da7e9317a83acdbd80ef45d94dca5eff76e727c67cdd`. That Linux binary successfully exercised the actual proxy configuration in a network-disabled Linux container; the verified Windows release also passed. No deployment image source was changed or published. Fresh GitHub Actions execution and complete Compose image builds remain REMOTE NOT RUN.

## J. Security and consistency assessment

M1 atomic deletion/confirmed-commit semantics, M2 claim/lease/fencing/reference guards, Fix 01 ownership/UUID behavior and B03 privacy remain. Default gates/certification close unsupported/unverified deployments. Read-only trusted certificates are mandatory, not a replacement for OS/IAM ownership or real account approval. Only constant/sanitized diagnostic fields are emitted. Metrics have no sensitive locator labels and are private at ingress.

Backup/restore never changes a stored cleanup locator. In-flight deletion safety requires verified external fencing/drain, not DB leases alone. Snapshot/restore is an operator maintenance workflow; absence of an Ops attestation or proof keeps it blocked. No bucket-wide orphan scan, version purge, queue drop, automatic requeue of processing/done or original-target restore access is introduced.

## K. Remaining Ops/Owner decisions

Approve target/account/TLS/policy, separate credentials and probe scope; assign certificate owner/read permissions/renewal and rotation; verify all ingress/legacy replicas/private networking; choose supervision/termination budgets; configure monitoring/log retention/receivers and test delivery; approve storage-side fence/drain procedure, backup encryption/RPO/RTO and restore-only credential boundary. All are still unverified for production.

## L. Production rollout blockers

No production/staging infrastructure approval or deployment was supplied. Intended-topology I01/I08/I20/I23 rehearsal and exact release-candidate PR/remote CI evidence remain required. No real provider IAM fence or remote-request drain is certified by local proxies. Local cleanup remains blocked by design. Keep the default UNVERIFIED record, profile/gates closed until all decisions and rehearsal results are approved.

## M. Unresolved findings / limits

- Local mount identity is addressed by prohibition, not a universal mount detector. Existing low-level local adapter placeholder limitation remains outside any supported cleanup deployment.
- Dev StrictMode refresh-cookie race and nine existing broader mypy errors were observed, not repaired outside this milestone.
- Caddy deployment image could not be pulled locally due to CDN EOF; same-version Linux/Windows native execution passed and CI pins the release binary. Full deployment image availability/build/bootstrap remains unverified. Bundled MinIO server/client references are unchanged; CI/test Chainguard evidence is not certification of those deployment images.
- Queue metrics are capped/cached and legacy document metrics are not bounded; no alert delivery or enterprise monitoring claim.
- Operator evidence/OS names need trusted platform authorization/audit. Certificate and quiescence files are not signed attestations.
- Restore supports SLRMS-sized objects through conditional single PUT; objects over 5 GiB are unsupported. Partial restore/probe compensation failures require operator investigation.
- No complete production Compose backup/restore/drain rehearsal or network filesystem outage was run. Do not mark I23 production gate passed on component evidence alone.

## N. Gemini review handoff (M3-T6)

Review against **M2 `26050fa`**, including every untracked source/test/runbook file in the complete patch. Prioritize default-closed gates and legacy ingress, local option B rejection, trusted certificate binding/expiry/principal, operator transaction+audit, bounded metrics/index migration, original-target isolation during restore, conditional no-overwrite PUT, process supervision/shutdown budgets and no-skip CI discovery. Reproduce with disposable PG/MinIO/Redis only; follow the operational runbook before considering any deployment. Independent review and Tech Lead/Owner approval precede any commit/push/rollout decision.
