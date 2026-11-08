# Fix 02 / M2 — Reliability and concurrency handoff

Local implementation for Tech Lead and Gemini review. No commit, push, PR, merge, production deployment or shared-data fault injection was performed. Production rollout remains an M3 gate.

## A. Git state

- Branch: `fix/storage-reliability-cleanup`.
- M2 base and unchanged HEAD: `ac8cbf7333571e7c89ffd23a57d1024aedd5e8c7` (approved M1 checkpoint).
- Integration base: `origin/develop`, `d23d939016cc5cd8541d6c4156b4b31ffbb78213`.
- Working tree was clean before M2. Final scope is 27 files (14 modified, 13 added), all unstaged. M1 was not amended, reset or rebased.

## B. Files modified/added

Modified (14 files):

```text
.github/workflows/ci.yml
backend/app/api/routers/documents.py
backend/app/core/config.py
backend/app/models/storage_cleanup.py
backend/app/repositories/document_repo.py
backend/app/repositories/storage_cleanup_repo.py
backend/app/services/document_dispatcher.py
backend/app/services/document_service.py
backend/app/services/storage.py
backend/app/tasks/document_processing.py
backend/tests/test_document_dispatcher.py
backend/tests/test_document_processing.py
backend/tests/test_document_task_retry.py
backend/tests/test_upload_folder_authorization.py
```

Added (13 files):

```text
backend/app/cleanup_worker.py
backend/app/services/storage_cleanup_service.py
backend/tests/integration/celery_fault_worker.py
backend/tests/integration/reliability_fault_process.py
backend/tests/integration/reliability_support.py
backend/tests/integration/s3_fault_proxy.py
backend/tests/integration/test_celery_redelivery.py
backend/tests/integration/test_cleanup_independence.py
backend/tests/integration/test_cleanup_postgresql.py
backend/tests/integration/test_local_reliability.py
backend/tests/integration/test_storage_reliability.py
backend/tests/test_storage_cleanup.py
docs/fix02-m2-reliability-concurrency-handoff.md
```

No dependency, frontend production source, local/staging/production Compose, processing enum, authentication policy or RAG algorithm was changed. `storage_backend` remains `String(20)`.

## C. Storage contract

Local deletion must open the configured root successfully before treating a missing target or intermediate directory as idempotent success. Root-open failures propagate, including `FileNotFoundError`; they are not evidence that the object is absent. Permission and I/O errors propagate as well. Paths must remain inside the configured root. POSIX deletion walks directory descriptors with `O_NOFOLLOW`, then unlinks through `dir_fd`; only `ENOENT` beneath the opened root is accepted as missing. A real parent-swap test verifies that replacing a directory with an external symlink cannot redirect unlink. This contract assumes that the accessible root still represents the intended backing filesystem; path-only locators cannot certify mount identity (see K and M).

Windows uses standard-library Win32 directory handles: `FILE_LIST_DIRECTORY`, reparse-point inspection, and read-only sharing. Every ancestor handle stays open until unlink completes, excluding rename and metadata writers. The root guard is outside the missing-entry handler; inside it only `ERROR_FILE_NOT_FOUND` (2) and `ERROR_PATH_NOT_FOUND` (3) are accepted. Network errors such as `ERROR_BAD_NETPATH` (53), although also represented by `FileNotFoundError`, propagate. A native Windows regression first demonstrated that metadata-only handles (`access=0`) do not enforce the intended sharing exclusion; the final guard uses real directory read access. The test verifies that a previously permitted writer is rejected with `ERROR_SHARING_VIOLATION` and rename is denied. Ordinary/missing/error propagation cases were also run on Windows. No new package is required.

S3 deletion confirms the bucket, accepts only exact `NoSuchKey` as an exceptional missing-object success, and propagates generic 404/missing-bucket/authorization failures. Cleanup additionally verifies versioning and Object Lock configuration before DELETE. Enabled/suspended versioning is blocked; supported Object Lock checks fail closed on unsupported/error responses. No production cleanup path lists a bucket or purges versions.

The worker compares all four stored locator components with the configured target. Changed backend, endpoint/root, bucket or invalid key is blocked rather than remapped. Filesystem errors during locator resolution reach the existing classifier: I/O/unavailable-root errors retry, while permission errors block; neither completes the job. Any live document referencing that target/key blocks physical deletion. Local references are compared after path resolution; S3 references use the exact immutable key. The valid upload workflow still generates a fresh UUID key and does not rename/reuse it.

Upload compensation now records its own failure using only the exception class, while preserving the original upload exception and the existing Fix 01 FK-to-404 classification. Durable recovery of failed-upload orphans remains outside Fix 02.

## D. Independent cleanup architecture

Entrypoint: `python -m app.cleanup_worker`.

This is a standalone polling process using PostgreSQL directly. It does not register a Celery cleanup task, use Redis, or depend on Celery Beat. The existing Celery worker remains responsible for document processing only.

Startup validates the target, PostgreSQL/table availability, retry bounds and S3 lease budget. It preserves PostgreSQL URL options (including search path) when adding connection/statement/lock timeouts. SIGINT/SIGTERM stop further polls; an active cycle completes before shutdown. Poll waits are interruptible. SDK clients and sessions are closed. Logs use stable event/key/value fields and never include raw exception text, credentials, signed URLs or document content.

## E. Claim, lease, retry and fencing

- Claim selects one due pending/retry job or expired processing lease using `FOR UPDATE SKIP LOCKED`.
- A fresh UUID token, processing status, incremented attempts and PostgreSQL lease expiry are flushed and committed before storage I/O.
- The claim is an immutable scalar snapshot. Reference-check read sessions also close before storage/filesystem I/O.
- Completion first acquires the job without waiting behind another claimant. It then conditionally updates by job ID, processing status, matching token and an unexpired lease using `clock_timestamp()`. This prevents an expiry predicate from aging while waiting for another row lock.
- Done/retry/blocked transitions all use this fence. An old token or expired lease cannot overwrite a fresh worker's result. A failed DB update/commit leaves recoverable durable state and is propagated, not relabelled as missing document/storage success.
- Initial due time now uses the existing M1 PostgreSQL server default. A test skews API-created timestamps to 2099 and verifies that committed pending work remains immediately claimable.

Defaults:

| Setting | Value |
| --- | --- |
| `CLEANUP_POLL_SECONDS` | 5 |
| `CLEANUP_LEASE_SECONDS` | 120 |
| `CLEANUP_CONNECT_TIMEOUT_SECONDS` | 5 |
| `CLEANUP_READ_TIMEOUT_SECONDS` | 15 |
| Cleanup SDK total attempts | 1 |
| `CLEANUP_RETRY_BASE_SECONDS` | 30 |
| `CLEANUP_RETRY_MAX_SECONDS` | 3600 |
| Jitter | 80–100% of capped exponential delay |

The exponent is capped before exponentiation. Cleanup has no retry-attempt retirement threshold. Transient timeouts/network/throttling/5xx and filesystem I/O failures retry; denied access, invalid targets/paths and unsupported storage configurations block. Unknown failures remain blocked for investigation. Database failures retain the lease for recovery.

These guarantees are **at least once**, with idempotent effects. A lease token fences PostgreSQL state; it cannot recall a DELETE already sent to storage.

## F. Processing and DELETE concurrency

Document processing writes now use short parent-document `FOR UPDATE` transactions. Starting processing/resetting chunks, adding a batch, writing status, setting task ID and preparing retry all recheck existence inside the same write transaction. They return snapshots/booleans rather than refreshed ORM objects.

Storage reads, extraction, long chunking, embeddings/LLM, broker dispatch and pacing sleeps run outside row locks/DB transactions. The pipeline checks existence between phases and returns `document_deleted` when cancellation is observed. Failure handling also writes by freshly locked document ID: a deleted document does not receive FAILED or an endless task retry. Real DB failures roll back and follow the existing processing retry policy instead.

Dispatcher presence checks release their transaction before publishing; task-ID persistence is guarded afterward. Retry authorizes owner/Admin against the locked row, keeps existing 401/403/404/409/422 contracts and serializes with DELETE. Upload captures the existing public response DTO before dispatch so transaction expiration/concurrent deletion cannot trigger an ORM refresh during serialization. Public response fields remain unchanged; internal storage paths are excluded.

The processing status enum is unchanged. M1 chat locking/ownership/read-only guards remain intact. No `revoke(terminate=True)` correctness mechanism was introduced; SIGKILL appears only in isolated crash tests.

## G. Acceptance evidence by scenario

| ID | Result and actual evidence |
| --- | --- |
| I04 | PASS — loopback HTTP proxy injects real 503 and read timeout in front of MinIO; SDK failure records retry, then real object deletion recovers. |
| I05 | PASS — a separate process executes the FastAPI DELETE via TestClient and hard-exits after the real PostgreSQL commit; document is gone and intent survives. |
| I06 | PASS — hard exit before API commit rolls back both writes; an uncommitted cleanup claim also rolls back. |
| I10 | PASS — a processing thread pauses at a controlled embedding barrier, DELETE commits on another PostgreSQL session, and late processing/failure handling stops without chunks/FAILED resurrection. |
| I11 | PASS — actual chunk INSERT holds the document lock; `pg_stat_activity` confirms DELETE waiting. After release, DELETE cascades committed chunks. Later chunks/status/task-ID writes return false. |
| I12 | PASS — process crash before/after claim commit; committed lease blocks immediate reclaim, expires by DB clock, then recovers with a new attempt. |
| I13 | PASS — proxy forwards DELETE to real MinIO, receives success, then drops the TCP response. Object is gone, job retries, missing-object replay becomes done. |
| I14 | PASS — hard exit after real S3 deletion but before completion leaves processing intent; expired-lease replay completes idempotently. |
| I15 | PASS — real concurrent PostgreSQL claims, skipped locked rows, wrong/expired token rejection, fresh-token recovery and stale completion rejection. Completion does not wait past expiry behind a locked row. |
| I16 | PASS — real Linux Celery prefork worker with Redis, production task and late acknowledgements. A verified child PID is SIGKILLed after DELETE; a new child receives `redelivered=true`, returns `document_deleted`, and creates no chunks. No eager mode. |
| I17 | PASS — dedicated Redis is stopped and Celery is absent; Redis ping fails, while a separate cleanup entrypoint deletes the real object, marks done and shuts down cleanly on SIGTERM. |
| I18 | PASS — PostgreSQL terminates the owned completion connection; DBAPI failure propagates, durable lease remains, recovery succeeds. No shared connection is killed. |
| I19 | PASS — real S3 authentication rejection and missing bucket block; invalid target/key checks and unknown SDK responses never become success. |
| I21 | PASS — actual Linux permission denial blocks; controlled OS EIO injection retries then recovers. Windows propagation/handle-sharing and POSIX symlink/parent-swap protections pass. |
| I22 | PASS — a real versioned bucket is blocked with versions retained and no delete marker added. All locator-component mismatches block without remapping. Object Lock rejection also has unit coverage. |
| I24 | PASS — another live document referencing the same object blocks cleanup; the real S3 object remains readable. |

PostgreSQL transactions/locks and S3 effects above use real services. Deterministic embedding providers and barriers avoid live AI calls. Some PostgreSQL-only bookkeeping cases use an object-storage spy; these do not substitute for the separate real-S3 crash/recovery evidence. API crash cases use real FastAPI routes in an OS subprocess through TestClient, not a deployed HTTP gateway. EIO is controlled fault injection, not a failing physical disk.

## H. Migration compatibility

No M2 migration or DDL change is needed. M1 already declares the server default used for `next_attempt_at`; only the Python-side override is removed. Upgrade from an empty dedicated database reached `f6a7b8c9d0e1`; `alembic check` reports no new upgrade operations and `alembic current` reports that revision as head. Column types, constraints, enum and indexes remain compatible with M1.

## I. Validation and regression

| Check | Actual result |
| --- | --- |
| Final full Windows backend discovery + PostgreSQL/S3 | 297 tests: 289 PASS, 8 platform/broker-mode skips |
| Linux acceptance batch | 47 PASS, 0 skipped |
| Separate broker-down entrypoint test | 1 PASS, 0 skipped |
| Native Windows handle-sharing regression | PASS after reproducing and fixing the exclusion gap |
| Backend coverage threshold 70% | PASS, 87% overall (3,022 / 3,469 statements) |
| Ruff `app tests alembic` | PASS |
| Mypy production-critical paths | 17 paths PASS with `--platform linux`; storage, cleanup service and worker PASS with `--platform win32` |
| Alembic upgrade | PASS on a fresh dedicated database, M1 head unchanged |
| Alembic check/current | PASS in the earlier M2 validation; not rerun for this correction |
| actionlint 1.7.12 (including shell analysis) | Earlier M2 PASS; CI unchanged in this correction, not rerun |
| Frontend lint/typecheck/production build | Earlier M2 PASS; not rerun for this backend-only correction |
| Local Edge/Playwright browser regression with mock API | Earlier M2 64 PASS; not rerun for this correction |
| Browser discovery | Earlier M2 193 tests / 13 files; not rerun for this correction |

The eight Windows discovery skips are one Linux-prefork case, five POSIX integration cases, one POSIX symlink unit case and the explicitly broker-down case. All eight acceptance cases are executed separately in the zero-skip Linux/broker-down groups. Windows handle tests are platform-specific and run on Windows. The full regression includes Fix 01 folder/UUID tests, M1 deletion/chat tests, retrieval, processing and dispatcher tests.

An initial full run had eight local-file assertions fail because the temporary harness forced S3 as the global default. The harness was corrected to keep LocalStorage defaults for those existing fixtures while real S3 suites remain explicitly enabled; assertions were not removed or weakened. Linux-target typechecking caught Windows-only attributes and now uses explicit platform guards. Native Windows handle testing caught the metadata-handle sharing gap; the regression was retained and passed after the implementation fix.

Representative commands actually executed (root `.venv`; backend commands run from `backend`):

```text
python .cache/fix02-m2/manage.py up
python .cache/fix02-m2/manage.py run -m alembic upgrade head
python .cache/fix02-m2/manage.py run-defaults -m coverage run --source=app -m unittest discover -s tests -p test_*.py -v
python .cache/fix02-m2/manage.py run-linux -m unittest tests.integration.test_cleanup_postgresql tests.integration.test_storage_s3 tests.integration.test_storage_reliability tests.integration.test_celery_redelivery tests.integration.test_local_reliability tests.test_storage_cleanup.LocalDeletionContractTestCase -v
python .cache/fix02-m2/manage.py redis-stop
# RUN_BROKER_DOWN_INTEGRATION=1, then restore the dedicated Redis in finally:
python .cache/fix02-m2/manage.py run-linux -m unittest tests.integration.test_cleanup_independence -v
python .cache/fix02-m2/manage.py redis-start
python .cache/fix02-m2/manage.py run -m alembic check
python .cache/fix02-m2/manage.py run -m alembic current
python -m coverage report --fail-under=70
python -m ruff check app tests alembic
python -m mypy app/core/config.py app/core/rate_limit.py app/models/document.py app/models/storage_cleanup.py app/repositories/document_repo.py app/repositories/storage_cleanup_repo.py app/services/document_service.py app/services/document_deletion_service.py app/services/storage.py app/services/storage_cleanup_service.py app/cleanup_worker.py app/services/document_dispatcher.py app/tasks/document_processing.py app/worker.py app/services/chat_service.py app/repositories/chat_repo.py app/schemas/chat.py --ignore-missing-imports --check-untyped-defs --explicit-package-bases
```

Frontend: `npm run lint`, `npm run typecheck`, `npm run build`. Browser tests ran `document-workspace.spec.js`, `document-upload.spec.js`, `folders.spec.js`, `chat-history.spec.js` against an owned loopback Next server with mock `http://localhost:8000` API responses, then `playwright test --list`. The owned server process tree was stopped afterward.

CI adds a disposable Redis service for real processing redelivery, enables PostgreSQL cleanup tests, typechecks the cleanup paths, and runs real storage/concurrency suites after MinIO readiness. Required integration steps reject any skip or empty suite. The broker-down step stops only its GitHub job's Redis container and restores it via EXIT trap. Existing lint, migration, coverage, frontend and pinned loopback MinIO steps remain.

## J. Remaining work / test limits

All listed M2 scenario IDs have local evidence. Not run: remote GitHub Actions (no push authorized), production/staging deployment/fault injection, real external AI calls, browser flows against a deployed backend/gateway, or a real mount/network-filesystem disconnection. Browser evidence uses mocks; backend API/transaction evidence uses real PostgreSQL. Root renames are real filesystem operations; backing I/O errors are injected. The separate placeholder probe simulates a changed namespace without mounting/unmounting a device. The actual production storage policy, mount identity, versioning and Object Lock settings have not been certified by these isolated tests.

Test-source helpers are in `backend/tests/integration`; local container management, logs and audit artifacts are ignored under `.cache/fix02-m2` and `.cache/fix02-m2-root-check`. Test containers used new labeled resources, loopback-only published ports and tmpfs, without existing volumes. All three fixture containers/network were removed after validating their ID/label/name; existing SLRMS containers remained stopped and their volumes/images were untouched. The earlier owned Next process tree was stopped and generated TypeScript build info was removed. No user data, cached image or shared bucket/database was removed. No dependencies were added. Upstream deprecation/TestClient stream warnings are visible in logs and were not suppressed to produce passing results.

## K. Risks and deferred M3 work

- At-least-once external effects: stale requests already sent to storage cannot be recalled. Keep UUID object keys immutable and never reuse them.
- Keep configured target/root/mount identity stable. Existing documents have no historical per-document target column; changed target jobs block instead of being remapped. **An empty placeholder at the same root path after backing-storage loss is not detected.** A path-only locator is unchanged even though the filesystem behind it is different, and `ENOENT` can still produce false success. The Linux namespace probe reproduced this residual risk with the original bytes retained. Safe mount identity/availability must be resolved and verified before enabling local cleanup on such deployments. No schema, mount sentinel, deployment guard or other M3 mechanism was introduced by this correction.
- Versioned/locked buckets are unsupported for purge and remain blocked. Verify the real rollout target/policy in M3.
- Blocked jobs require investigation; operator requeue CLI, alerts, metrics and dashboards remain M3. Jobs are not pruned on retry exhaustion.
- Production cleanup deployment, supervision, least-privilege storage permissions and shutdown budgets remain M3. Worker S3 verification requires bucket configuration read permissions as well as object deletion permission.
- Failed-upload orphan recovery is a separate follow-up; this milestone preserves the original error and records compensation failure without claiming durable upload-orphan recovery.
- Retention, undelete, backup/restore automation and global storage scanning were not introduced.

## L. Gemini review handoff

Review M2 against `ac8cbf7333571e7c89ffd23a57d1024aedd5e8c7`, not a combined M1+M2 diff against develop. Include untracked new source/tests when reviewing `git diff`. A complete local review patch/audit is stored under ignored `.cache/fix02-m2` after final validation.

Prioritize: root-open failures outside the missing-entry handler; platform-specific missing-entry classification; root-unavailable job state; the residual placeholder/mount-identity risk; no DB transaction across storage/LLM/broker I/O; claim commit before I/O; completion lock/clock/token fencing; bucket/target/reference validation; Windows share-access and POSIX dir_fd protections; original upload error preservation; every processing mutation's document lock/existence check; real redelivery and broker-down evidence; skip guards and service cleanup. M1 chat guards and Fix 01 ownership/UUID behavior must remain intact. The patch is ready for independent code review with the disclosed limitation; it is not a production safety approval. Tech Lead review and independent approval precede any commit/deployment decision.

## M. Pre-review root availability correction (2026-11-09)

Finding confirmed against the exact 27-file M2 handoff (prior patch SHA256 `9345d267e413af0fa0930577c6e3e94c766cd8e7636259d91c832d6afb922dea`). Before changing production code, the new regressions failed on Windows (9 tests, 3 failures, 1 POSIX skip) and Linux/PostgreSQL (11 tests, 4 failures, no skips). The original broad `FileNotFoundError` handler covered both root opening and entry deletion. A real root rename retained the file on an offline sibling path, yet `LocalStorage.delete()` returned normally and the real PostgreSQL job became `DONE`. Locator-resolution EIO was also incorrectly converted into an invalid-locator `BLOCKED` result.

The correction changes five files relative to that handoff: `storage.py`, `storage_cleanup_service.py`, `test_storage_cleanup.py`, `integration/test_local_reliability.py`, and this document. No other previous M2 blob changed. Eight regression methods were added: three common adapter tests, one native-Windows network-error test, and four cross-platform PostgreSQL outcome tests. The existing CI Linux module selection discovers the new PostgreSQL cases and rejects skips without any additional CI edit.

| Scenario | Adapter / PostgreSQL outcome | Evidence and limits |
| --- | --- | --- |
| Target absent under accessible, intended root | Idempotent success / `DONE` | Real filesystem deletion/missing-object replay on Linux; adapter also exercised on Windows. |
| Intermediate directory absent under accessible, intended root | Idempotent success / `DONE` | New PostgreSQL case on Linux and Windows; existing adapter test retained. |
| Root absent while original backing file remains | Exception / `RETRY`, `completed_at` remains null | Actual root rename on Linux and Windows; restore root, make job due, retry and complete deletion. |
| Root open reports ENOENT | Exception / `RETRY` | Injected adapter error plus the real root-rename PostgreSQL case. |
| Existing root reports backing EIO | Exception / `RETRY`, bytes retained | Controlled root-open EIO on Linux/Windows; recovery becomes `DONE`. Target-lookup EIO also propagates in adapter tests. |
| Locator resolution reports EIO | Exception / `RETRY`, bytes retained | Controlled failure with real PostgreSQL outcome, both platforms; no invalid-target relabelling. |
| Permission denied | Exception / `BLOCKED`, never `DONE` | Actual Linux privilege drop and denied access; Windows adapter injects permission failure. |
| Windows network-path-not-found (`winerror=53`) | Exception, not missing-object success | Native Windows adapter branch with injected OS error; no actual network-share outage was performed. |
| Existing root replaced by an empty placeholder, old backing retained | **Not guaranteed: adapter still returns success** | Linux namespace simulation: root exists, inode changed, locator unchanged, old object retained. This is a documented risk probe, not a passing deletion acceptance case or real unmount. |

After the correction, targeted Windows storage/PG tests passed 24/25 with only the POSIX symlink case skipped; targeted Linux adapter/local-PG tests passed 16/16 with no skips. Broader final reruns passed 297 Windows tests (289 pass, 8 expected skips), 47 Linux acceptance tests (zero skips), and the separate broker-down test (1 pass, zero skips). Ruff and both platform mypy checks passed. Current coverage and validation counts are in I.

Focused commands actually run from the repository root, using a temporary isolated-services harness:

```text
python .cache/fix02-m2/manage.py run-defaults -m unittest tests.test_storage_cleanup tests.integration.test_local_reliability.LocalRootAvailabilityTestCase -v
python .cache/fix02-m2/manage.py run-linux -m unittest tests.test_storage_cleanup.LocalDeletionContractTestCase tests.integration.test_local_reliability -v
python .cache/fix02-m2/manage.py run-defaults -m coverage run --data-file=../.cache/fix02-m2-root-check/.coverage --source=app -m unittest discover -s tests -p test_*.py -v
python .cache/fix02-m2-root-check/placeholder_probe.py
```

The earlier handoff blobs/audit/patch and red/green test logs are retained locally in ignored `.cache/fix02-m2-root-check`. The complete regenerated tracked+untracked M2 patch is `.cache/fix02-m2/m2-review.patch`; the incremental five-file correction is `.cache/fix02-m2-root-check/correction-review.patch`. Neither patch includes the harness, runtime state, logs, credentials, cache, or test artifacts. Patch generation does not stage files. No M3 implementation was performed.
