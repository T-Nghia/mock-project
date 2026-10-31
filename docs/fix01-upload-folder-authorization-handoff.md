# Fix 01: Upload folder authorization — review handoff

## A. Task completion and Git baseline

- Implemented SEC-01 (folder ownership), CORR-01 (UUID validation), and the
  authorization-to-INSERT deletion race handling approved by the user.
- Before: `develop` at `497f3ff27b7c67da20b2298d57d30ddd200df459`.
- Fetched `origin/develop`; verified `cd016ea` is an ancestor and the working tree
  was clean before creating the fix branch.
- `develop` was already current; `git merge --ff-only origin/develop` made no changes.
- After: `fix/upload-folder-authorization`, same HEAD; base is `origin/develop`.
- Backend/frontend source at this base matches `cd016ea` (`git diff cd016ea HEAD
  -- backend frontend .github` was empty).
- No implementation commits, push, or merge commits were created.

## B. Files changed

| File | Purpose |
| --- | --- |
| `backend/app/api/routers/documents.py` | Typed optional UUID Form and authorization dependency wiring. |
| `backend/app/services/document_service.py` | Ownership preflight, release read transaction, classify only the folder FK error. |
| `backend/app/repositories/document_repo.py` | Roll back failed add/INSERT/commit and re-raise. |
| `backend/tests/test_documents.py` | Ownership, Admin/Student behavior, UUID/empty/missing fields, no rejection side effects. |
| `backend/tests/test_upload_folder_authorization.py` | Fail-closed dependency, ordering, cleanup, negative classifier and repository rollback tests. |
| `backend/tests/integration/test_upload_folder_authorization.py` | Real PostgreSQL constraint/race/rollback evidence, including the upload endpoint. |
| `.github/workflows/ci.yml` | Explicit test DSN so the new PostgreSQL suite runs in CI discovery. |
| `e2e/tests/document-upload.spec.js` | UI handling of 404/string and 422/validation-array responses. |
| `e2e/tests/library-upload-fixture.js` | Allow the upload mock to return the supplied error detail. |
| `docs/fix01-upload-folder-authorization-handoff.md` | Implementation and validation evidence for Gemini. |

## C. Implementation details

- `folder_id: uuid.UUID | None = Form(default=None)` uses FastAPI 0.111.0 /
  Pydantic 2.7.1 validation. Malformed UUID returns 422. Omitted and empty form
  values still produce an unfiled upload.
- `DocumentService.save_upload` calls `FolderRepository.get_owned(folder_id,
  uploaded_by)` before writing storage, document metadata, or tags. Admin has no
  bypass. Missing/unowned folders share the same 404 response. Student is still
  blocked by the existing permission dependency.
- Uploading with a folder and no authorization repository raises `RuntimeError`
  before any writes; existing non-upload service callers need no new dependency.
- Authentication and ownership checks share the request session and perform only
  reads. After file validation, `rollback()` ends this read transaction before
  external object I/O. No row locks are introduced. The actor UUID is already
  captured before ORM expiration. Review this assumption if adding upload callers
  that stage unrelated writes in the same session.
- `DocumentRepository.create` rolls back failures from add/INSERT/commit. The
  existing storage-delete-on-create-failure path is retained.
- Only SQLAlchemy `IntegrityError` wrapping psycopg2 `ForeignKeyViolation`, with
  `diag.table_name == "documents"` and
  `diag.constraint_name == "documents_folder_id_fkey"`, becomes 404. The classifier
  also requires a supplied folder ID. No dynamic reflection or error-message
  matching is used: psycopg2 is the pinned driver, and tests verify the constraint
  from the actual Alembic-migrated PostgreSQL schema.
- Other database errors are re-raised. The service never silently clears the
  requested folder ID.
- No migration, dependency declaration, frontend production code, Celery behavior,
  chat deletion, or storage cleanup architecture was changed.

## D. Validation actually performed

Backend commands were run from `backend` with `..\.venv\Scripts\python.exe`.
Frontend commands were run from `frontend` with the cached Node 22.23.4 runtime.
The local host uses Python 3.12.10; CI remains Python 3.11 / Node 20.

| Command / group | Result |
| --- | --- |
| `python -m alembic upgrade head` | PASS; all existing migrations applied to the disposable PostgreSQL DB. |
| `python -m unittest tests.test_upload_folder_authorization tests.test_documents tests.test_folders tests.test_document_processing tests.test_document_dispatcher tests.test_document_task_retry -v` | PASS, 54 tests. |
| `python -m unittest tests.integration.test_upload_folder_authorization -v` | PASS, initial 6 PostgreSQL tests; the subsequent endpoint race test also passed in full discovery. |
| `python -m coverage run --source=app -m unittest discover -s tests -p "test_*.py" -v` | PASS, 183 discovered, 182 passed, 1 skipped; includes all 7 new PostgreSQL tests and existing pgvector integration tests. |
| `python -m coverage report --fail-under=70` | PASS, total 85% (document service 93%). |
| `python -m ruff check app tests alembic` | PASS. |
| `python -m mypy app/core/config.py app/core/rate_limit.py app/models/document.py app/repositories/document_repo.py app/services/document_service.py app/services/storage.py app/services/document_dispatcher.py app/tasks/document_processing.py app/worker.py --ignore-missing-imports --check-untyped-defs --explicit-package-bases` | PASS, 9 source files. |
| `npm run lint` | PASS, no warnings/errors. |
| `npm run typecheck` | PASS. |
| `npm run build` | PASS, 14 generated pages. |
| `playwright test --list` | PASS, 181 tests in 12 files; discovery only. |
| `playwright test tests/document-upload.spec.js tests/folders.spec.js --reporter=line` | PASS, 34 tests, Microsoft Edge headless via Playwright 1.55.0. |
| `git diff --check` and no-index whitespace checks for new files | PASS. |

The Playwright commands used the existing CLI under
`.cache/slrms-tools/qa/node_modules/@playwright/test/cli.js` with `NODE_PATH` pointing
to that dependency directory. The app ran locally at `http://127.0.0.1:3101`.
Full test logs are local ignored artifacts under `.cache/fix01/`:
`regression.log`, `backend-full.log`, `playwright-list.log`, and
`playwright-upload-folders.log`.

Test boundaries:

- Unit tests mock dependencies and driver diagnostics for control-flow cases.
- Existing document API tests use SQLite and mocked embedding, consistent with
  the repository's API test setup; these do not establish FK/race behavior.
- New integration tests use actual PostgreSQL/psycopg2. Only object storage and
  endpoint dispatch are mocked. One session authorizes, another session deletes
  and commits during `save_stream`, then the real INSERT fails with SQLSTATE
  `23503`. The service returns 404, cleanup runs once, tags/documents are absent,
  the session is usable, and the endpoint never dispatches. A one-second delete
  lock timeout and checks on session transaction state guard against holding the
  read transaction or row locks across object upload.
- Real PostgreSQL uploader FK (`23503`), UNIQUE (`23505`), and NOT NULL (`23502`)
  failures remain database errors and also exercise rollback/cleanup.
- Browser tests mock the API; they verify multipart fields, existing upload/folder
  behavior, error display, preserved form metadata, and explicit retry.

The PostgreSQL 16.14 DB ran in a dedicated temporary container using
`pgvector/pgvector:pg16`, with separate credentials/data and loopback-only port
51293. Existing migrations were applied before testing. Each new integration test
creates and drops its own generated `upload_folder_test_<uuid>` schema; no shared
application tables are truncated. A final query found zero leftover test schemas.
No shared/staging database was used.

Initial sandbox attempts failed on Windows temporary-directory writes and Node
worker spawning (`spawn EPERM`). The same checks passed outside the sandbox;
tests were not weakened to bypass those failures. Port 55432 was unavailable, so
Docker assigned loopback port 51293. Docker Desktop was started for the test run.

## E. Known issues and limits

- The existing real S3 integration test was skipped because
  `RUN_S3_INTEGRATION=1` was not enabled. Cleanup call ordering/count is tested;
  this run does not establish real object-storage deletion behavior.
- No staging smoke/lifecycle tests, live browser-to-backend deployment tests,
  Docker image builds, or remote GitHub Actions run were performed.
- Existing third-party deprecation warnings remain outside this fix's scope.
- The existing cleanup path can still fail independently of the database error;
  changing that architecture was explicitly excluded.
- A manually renamed deployment FK or a different driver would need a classifier
  update. Unknown errors remain errors rather than being reported as a folder 404.

## F. Gemini review handoff and reproduction

Review base: `origin/develop` at `497f3ff27b7c67da20b2298d57d30ddd200df459`.
Review branch: `fix/upload-folder-authorization`; all implementation changes are
uncommitted. Use `git diff origin/develop` for tracked changes and `git status
--short` for the new test/report files, which must also be reviewed.

Review ownership ordering, no Admin bypass, optional dependency fail-closed
behavior, the read-only rollback before object upload, exact psycopg2 constraint
classification, cleanup on failure, and the two-session PostgreSQL evidence.

To reproduce the database tests, provision a **dedicated** PostgreSQL/pgvector test
DB, then set both `DATABASE_URL` and `UPLOAD_FOLDER_TEST_DATABASE_URL` to its
`postgresql+psycopg2://...` DSN. From `backend`, run the existing migrations followed
by the integration or full-suite commands above with `ENV=test` and
`STORAGE_BACKEND=local`. The new suite intentionally skips without its explicit
test DSN. CI supplies that DSN to the existing isolated CI PostgreSQL service.

For browser tests, run the frontend locally, set `APP_URL` to its URL,
`UI_BROWSER_CHANNEL=msedge` for the installed local browser, and run the two
selected specs. The fixture expects the frontend API base URL to be
`http://localhost:8000`. API/SMOKE placeholder variables are needed only for
module discovery; selected browser specs route API requests to fixtures.

Final source state: seven modified existing files and three new files (listed
above), no staged changes. Generated `frontend/tsconfig.tsbuildinfo` was removed.
The temporary app server and test container are stopped after verification.
