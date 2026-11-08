# Fix 02 / M1 — Durable deletion core

Status: local implementation and validation for independent review. **Do not deploy M1 to production: the cleanup worker does not exist yet.** No commit, push, PR creation, merge, or deployment was performed.

## A. Git state

- Before: clean `develop`, HEAD `d23d939016cc5cd8541d6c4156b4b31ffbb78213` (PR #18 merge).
- Fetched `origin/develop`; local and remote baseline matched. The new branch name was absent locally and on origin.
- After: `fix/storage-reliability-cleanup`, same HEAD; base `origin/develop`. Changes remain unstaged for review.
- `.env`, Docker Compose, existing storage volumes/images, production requirements, processing tasks and dispatcher were not changed.

## B. Files

| Area | Files | Purpose |
| --- | --- | --- |
| Queue | `backend/app/models/storage_cleanup.py`, `backend/app/repositories/storage_cleanup_repo.py`, `backend/app/models/__init__.py` | Register durable intent; staging-only repository |
| Migration | `backend/alembic/versions/f6a7b8c9d0e1_add_storage_cleanup_jobs.py` | Add queue and indexes; protect nonempty queue on downgrade |
| Document deletion | `backend/app/services/document_deletion_service.py`, `backend/app/repositories/document_repo.py`, `backend/app/api/routers/documents.py`, `backend/app/services/document_service.py` | Atomic deletion service; remove the old commit-then-storage-delete path |
| Chat backend | `backend/app/api/routers/chat.py`, `backend/app/repositories/chat_repo.py`, `backend/app/services/chat_service.py`, `backend/app/schemas/chat.py` | Independent private history; nullable document ID; concurrency checks |
| Backend tests | `backend/tests/test_document_deletion.py`, `backend/tests/integration/test_document_deletion.py`, `backend/tests/test_documents.py`, `backend/tests/test_chat.py`, `backend/tests/test_chat_service.py`, `backend/tests/test_chat_schemas.py` | Transaction, API, PostgreSQL, orphan and regression evidence |
| Chat UI | `frontend/app/(app)/chat/page.tsx`, `frontend/app/(app)/chat/[id]/page.tsx`, `frontend/components/chat/chat-panel.tsx` | Paginated history, transcript, session deletion and orphan read-only state |
| Navigation and contract | `frontend/components/layout/sidebar.tsx`, `frontend/components/layout/app-shell.tsx`, `frontend/lib/api.ts`, `frontend/lib/types.ts` | Independent history navigation and API types |
| Document dialog | `frontend/components/documents/delete-document-button.tsx` | Explain that chat history and citation snapshots are retained |
| Browser tests | `e2e/tests/chat-history.spec.js`, `e2e/tests/document-workspace.spec.js`, `e2e/tests/app-shell.spec.js`, `e2e/tests/document-lifecycle.spec.js` | History/UI states, stale workspace, navigation, updated lifecycle expectations |
| CI | `.github/workflows/ci.yml` | Enable dedicated PostgreSQL deletion tests and typecheck new critical paths |
| Handoff | This document | Scope, validation, limitations and review instructions |

## C. Migration and schema

Revision `f6a7b8c9d0e1` follows `e5f6a7b8c9d0`. The additive table `storage_cleanup_jobs` contains:

- UUID `id` primary key, unique UUID `document_id`, UUID `requested_by`.
- `storage_backend`, `storage_target_identity`, `storage_bucket_or_root`, `object_key_or_location`.
- `status`, `attempts`, `next_attempt_at`, `lease_token`, `lease_expires_at`.
- `created_at`, `updated_at`, `completed_at`, `last_error_code`, `last_error_message`.

Document/requesting-user IDs are snapshots with **no foreign keys**. Status is constrained to `pending`, `processing`, `retry`, `blocked`, `done`; attempts cannot be negative. Initial state is pending with zero attempts. Timestamp columns use timezone-aware PostgreSQL types. Lease/completion/error fields start null.

Partial indexes support due pending/retry jobs and processing jobs with expiring leases. No pruning is implemented. Downgrade refuses to drop any nonempty queue, including unfinished intent. ORM updates refresh `updated_at`; a future worker using raw SQL must update it explicitly.

An empty, dedicated PostgreSQL/pgvector database was migrated from the initial revision through this head. Tests inspect the migrated public schema, not only ORM metadata. Downgrade protection was exercised against a disposable test schema.

## D. Transaction implementation

`DocumentDeletionService` owns the business transaction. It accepts the existing read-only authentication autobegin. It rejects sessions with autoflush enabled, pending ORM writes, nested/explicit transactions, inactive state, or an externally owned connection transaction. It does not add `session.begin()` or a savepoint.

1. Capture authenticated actor ID/role.
2. Read the document with `SELECT ... FOR UPDATE`, refreshing existing ORM state.
3. Authorize the owner or Admin against the locked row.
4. Snapshot the configured storage target and document locator without contacting storage.
5. Stage the cleanup job and hard document deletion through repositories that do not commit.
6. Flush both changes, then commit exactly once.

Failures before commit roll back the transaction. A failed commit is propagated after resetting the session; the log explicitly says the outcome may be unknown. A lost acknowledgement is never presented as proof of rollback or returned as HTTP 204. A unit test simulates commit success followed by lost acknowledgement and verifies that intent remains present while the call fails.

Local locators retain the resolved root and relative object path; paths outside the root fail closed. S3 locators retain a credential-free endpoint (or AWS region identity), bucket and object key. Endpoint userinfo/query/fragment and object URLs are rejected. No access keys, secret keys, signed URLs or document contents are stored.

## E. DELETE behavior

| Case | Result |
| --- | --- |
| Owner Teacher or Admin deletes an existing document | 204 only after confirmed commit |
| Student | Existing RBAC 403 |
| Another Teacher | 403; no intent or storage deletion |
| Missing authentication | 401 |
| Malformed UUID | 422 |
| Missing document or repeated DELETE | 404; no duplicate intent |
| Database failure | Error/500; never relabelled as document-not-found |

HTTP 204 now means metadata is hard-deleted and cleanup intent is durable. The physical object remains until M2 processes the queue. DELETE never constructs a storage client or calls its delete method.

Existing PostgreSQL FKs delete chunks, document-tag associations, bookmarks, comments and ratings. Tag records remain. Chat sessions become orphaned via `document_id = NULL`; messages and citation JSON snapshots remain. Explicit session deletion cascades messages.

## F. Chat API and UI

- New `GET /chat/sessions?limit=20&offset=0`: owner-only envelope `{items,total,limit,offset}`. Limit range 1–100; nonnegative offset. Deterministic newest-first ordering.
- Existing list-by-document endpoint is retained.
- Session response `document_id` is nullable. Legacy orphan sessions can be listed, read and deleted without a document lookup. No Admin bypass permits reading/deleting another user's chat.
- POST message on an orphan returns 409 before writing a message or calling retrieval/provider. Explicit session DELETE returns 204, then 404 on repetition.
- Session creation locks the document before inserting its FK reference. Message acceptance and answer persistence lock document then session. Transactions are released before retrieval and LLM calls; state is checked again before persistence.
- Deletion during retrieval prevents a provider call when detected. Deletion during generation discards the stale answer (409 for deleted document; 404 for deleted session). An already accepted user message remains part of preserved history.
- `/chat` provides private paginated history, loading/error/retry/empty states and session-delete confirmation. `/chat/[id]` displays transcript and saved citation text. Orphans have no composer or links to removed document/chunks. Live transcripts link back to the document workspace.
- A workspace receiving 409 refreshes its transcript and disables message entry. Document confirmation explains KEEP CHAT.

This is not a claim of complete concurrency coverage: deletion can begin immediately after the pre-provider check, and an already in-flight external request cannot be recalled. Post-provider validation prevents persisting the stale answer. Processing/task guards remain M2 work.

## G. Validation

Executed locally, using Windows Python 3.12, PostgreSQL 16/pgvector in a new disposable Docker container, and local Next.js with mocked browser API responses.

| Check | Actual result |
| --- | --- |
| Alembic upgrade from blank dedicated PostgreSQL DB | PASS |
| New PostgreSQL deletion/concurrency integration suite | 17 PASS, 0 skipped |
| Full backend discovery under coverage | 231 tests: 230 PASS, 1 skipped |
| Backend coverage threshold 70% | PASS, 86.09% overall |
| Chat unit/API/schema/repository group | 37 PASS |
| Ruff `app tests alembic` | PASS |
| Mypy 15 production-critical paths | PASS |
| GitHub Actions actionlint 1.7.12 | PASS |
| Frontend lint and typecheck | PASS |
| Frontend production build | PASS |
| Browser tests with mock API | 81 unique tests PASS: 36 app-shell/workspace + 11 chat-history + 34 upload/folders |
| Playwright discovery | 193 tests / 13 files |

The full backend run includes the 17 new real-PostgreSQL tests, Fix 01 PostgreSQL tests, pgvector retrieval tests, upload/UUID/permission tests, processing and dispatcher regression. The one skip is existing `RUN_S3_INTEGRATION` opt-in storage integration; no real S3 server was started for this M1 run. The existing CI S3 job and no-skip guard are preserved.

Real PostgreSQL evidence uses psycopg2, injected database triggers for INSERT/DELETE/deferred-COMMIT failures, and `pg_stat_activity` lock waits for concurrent DELETE/session creation. Storage and provider spies/mocks establish absence of calls and deterministic timing; they do not replace PostgreSQL transaction or lock evidence. No live LLM request was made.

Commands run (paths relative to repository, Python tooling in root `.venv`):

```text
python .cache/fix02-m1/manage_pg.py up
python .cache/fix02-m1/manage_pg.py run -m alembic upgrade head
python .cache/fix02-m1/manage_pg.py run -m unittest tests.integration.test_document_deletion -v
python .cache/fix02-m1/manage_pg.py run -m coverage run --source=app -m unittest discover -s tests -p test_*.py -v
# In backend:
python -m coverage report --fail-under=70
python -m ruff check app tests alembic
python -m mypy app/core/config.py app/core/rate_limit.py app/models/document.py app/models/storage_cleanup.py app/repositories/document_repo.py app/repositories/storage_cleanup_repo.py app/services/document_service.py app/services/document_deletion_service.py app/services/storage.py app/services/document_dispatcher.py app/tasks/document_processing.py app/worker.py app/services/chat_service.py app/repositories/chat_repo.py app/schemas/chat.py --ignore-missing-imports --check-untyped-defs --explicit-package-bases
# In frontend:
npm run lint
npm run typecheck
npm run build
# In e2e, with APP_URL=http://127.0.0.1:3001 and UI_BROWSER_CHANNEL=msedge:
node ../.cache/slrms-tools/qa/node_modules/playwright/cli.js test tests/chat-history.spec.js tests/document-workspace.spec.js tests/app-shell.spec.js --reporter=line
node ../.cache/slrms-tools/qa/node_modules/playwright/cli.js test tests/chat-history.spec.js tests/document-upload.spec.js tests/folders.spec.js --reporter=line
node ../.cache/slrms-tools/qa/node_modules/playwright/cli.js test --list
# Back at repository root, after verification:
python .cache/fix02-m1/manage_pg.py down
git diff --check
```

Frontend tools used cached Node 22.23.4 and Playwright with `NODE_PATH` pointing to `.cache/slrms-tools/qa/node_modules`; the local Next server bound `127.0.0.1:3001`. Discovery additionally used test-only placeholder smoke settings; discovery does not execute the real-backend lifecycle tests. The 36 workspace/shell tests passed in the first browser run, and the final 45-test run passed all 11 history and 34 upload/folder tests. The new `/chat` routes were included in the successful production build.

The local PostgreSQL helper is an ignored verification artifact, not a production dependency. For independent reproduction, create a **new dedicated** PostgreSQL/pgvector test database, set `DATABASE_URL`, `DELETE_TEST_DATABASE_URL`, `UPLOAD_FOLDER_TEST_DATABASE_URL`, `ENV=test` and a test-only JWT key, migrate it, then run the backend commands above. Never point these suites at staging or production. CI supplies the new opt-in variable from its existing disposable database service.

Initial sandbox runs could not write temporary files/spawn browser processes; authorized local reruns passed. Four initial new browser-test assertions were corrected to scope transcript elements and respect the existing sanitized error contract; all new chat tests were rerun successfully. Production source was not changed to hide those assertion failures.

Not run: real-backend Playwright lifecycle/staging tests, live LLM integration, live S3 integration, production migration/deployment, worker/retry/lease operation, or post-push GitHub Actions. The lifecycle test source was updated to assert retained orphan history but was not run against shared staging.

## H. Diff summary

32 files: 22 modified and 10 added, implementing only M1-T1, M1-T2 and M1-T3 with their tests and CI enablement. Review both `git diff` (tracked changes) and `git ls-files --others --exclude-standard` (new source/tests); new files are deliberately unstaged. A complete local review patch is available at ignored `.cache/fix02-m1/m1-review.patch`. Ignored logs, helper scripts and coverage reports are not deliverable source. No dependencies were added. The dedicated PostgreSQL container and local Next server were stopped/removed; existing SLRMS containers and volumes were untouched, and the generated TypeScript build-info file was removed.

## I. Outstanding M2/M3 scope

- Physical cleanup worker, claiming/retry/backoff/lease behavior and crash recovery.
- Comprehensive Celery processing cooperative-cancellation guards.
- Cleanup observability, alerts and metrics.
- Versioning/Object Lock verification and all-version deletion decisions.
- Production rollout gate and operational recovery procedures.

No retention, undelete, orphan scanner or backup automation was added. Existing production requirements were not rewritten.

## J. Risks and recommendation

- **Do not roll out M1 alone.** Queued objects remain on storage without M2.
- Locators snapshot the current configured backend. Existing documents have no per-document historical backend/target column; changing storage targets before deletion is not resolved here. Keep target/root configuration stable and ensure future local workers share the API's filesystem mount.
- S3 versioning/Object Lock may retain data after an eventual ordinary delete; M3 must validate actual deployment policy.
- A lost COMMIT acknowledgement is inherently ambiguous. The client receives failure; operators must inspect document/intent state rather than assuming rollback.
- In-flight LLM work can finish after deletion; its answer is discarded. Full processing cancellation is not implemented.
- No observed blocking local-test failure remains. Recommendation: independent M1 review, then M2; keep production rollout blocked until the complete solution is validated.

## K. Gemini review handoff

Base: `origin/develop` at `d23d939016cc5cd8541d6c4156b4b31ffbb78213`. Review branch: `fix/storage-reliability-cleanup`.

Prioritize transaction ownership/autobegin contract, FOR UPDATE lock order, single commit and unknown-outcome behavior, locator completeness/secret exclusion, queue survival and downgrade protection, orphan ownership/409/no-provider behavior, and frontend saved-citation/read-only behavior. Read the PostgreSQL tests alongside the services, then inspect all new untracked files. Confirm the existing Fix 01 authorization/UUID logic and production Compose remain unchanged.
