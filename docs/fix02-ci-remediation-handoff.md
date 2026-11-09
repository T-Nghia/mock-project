# Fix 02 — I16 remote CI remediation handoff

Base: `e54a5ce0380e83d50f16a4b093ea2e03e21f69b6`, branch
`fix/storage-reliability-cleanup`. Local verification: 2026-11-09.
Recommendation: **READY FOR FIX COMMIT, subject to Tech Lead review**.
No staging, commit, push, PR, merge or deployment is performed in this task.
Remote validation remains blocked until an approved follow-up commit runs CI.

## A. Exact failure and root cause classification

Remote evidence:
[CI run](https://github.com/T-Nghia/mock-project/actions/runs/42561469620),
[backend job](https://github.com/T-Nghia/mock-project/actions/runs/42561469620/job/128978606105).
I16 exited code 1 before `ready-*.json`; the original run did not exercise SIGKILL
or redelivery. Its temporary worker log was not retained as an artifact.

Classification: **B — dependency incompatibility / incomplete Redis transport
dependencies in the freshly resolved environment**. Not an application import
path, file permission, readiness race, processing-logic or storage-architecture fix.
No flaky-test claim is made.

A new non-root Linux Python 3.11.18 virtualenv, installed from the unchanged
requirements, resolved the same relevant versions as GitHub:

| Package | Remote / clean reproduction | Fixed clean virtualenv |
| --- | --- | --- |
| Celery | 5.4.0 | 5.4.0 |
| Kombu | 5.7.0 | 5.6.2 |
| Billiard | 4.3.2 | 4.3.2 |
| Click | 8.5.1 | 8.5.1 |
| redis-py | 5.0.4 | 5.0.4 |
| packaging | absent | 26.3, required by Kombu 5.6.2 |

The unchanged I16 test reproduced the original failure. A local wrapper captured
only a bounded sanitized tail before its temporary directory was removed:

```text
celery_fault_worker.py:64 -> celery_app.worker_main(...)
celery/worker/worker.py:119 -> self.app.connection_for_read()
kombu/connection.py:248 -> get_transport_cls(transport)
kombu/transport/redis.py:119 -> from packaging.version import Version
ModuleNotFoundError: No module named 'packaging'
```

Kombu 5.7.0 metadata declares `packaging==26.3` only in its Redis extra, while
Celery's plain dependency permits `kombu>=5.3.4,<6.0`. The project installed plain
Celery plus a separately pinned redis-py, so the resolver selected Kombu 5.7.0
without that optional extra.

An isolated packaging-only probe proved that installing packaging alone is
insufficient:

```text
kombu/transport/redis.py:2072 -> raise VersionMismatch(...)
kombu.exceptions.VersionMismatch: Redis transport requires redis-py versions
6.1.0 or later. You have 5.0.4
```

That release's Redis extra metadata is even stricter (`redis>=6.4.0,<9.0.0`),
whereas Celery 5.4's Redis extra accepts `redis>=4.5.2,<6.0.0` excluding 4.5.5.
Changing extras or adding packaging alone would not produce a supported client
combination. The probe exited before readiness even when Celery returned code 0;
the unchanged `poll() is None` guard correctly rejected that outcome.

Kombu 5.6.2 declares packaging as an unconditional dependency and its Redis extra
accepts the existing 5.0.4 client. A clean install and real I16 prove that combination.
No Redis/Celery upgrade or speculative dependency pin was applied.

## B. Phase A startup audit

- Test command: current interpreter, `-m tests.integration.celery_fault_worker`,
  owned temporary directory and UUID queue; working directory is backend.
- Child inherits the fixture environment, overrides a UUID PostgreSQL search path,
  keeps `ENV=test`, supplies S3 fixture credentials and blanks external AI keys.
- Worker imports `app.worker.celery_app`; broker is
  `CELERY_BROKER_URL or REDIS_URL`, JSON serializers, eager mode disabled. No result
  backend is configured; test completion evidence comes from signals/marker files.
- Prefork concurrency remains one. Signals write a temporary JSON file then
  atomically replace the marker. The failing process exited before those signals;
  after the dependency fix the same paths/permissions/guard work unchanged.
- GitHub ran Ubuntu 26.04.1, runner image `ubuntu-26.04` / `20261101.186.1`.
  Reproduction uses Linux/WSL2 containers, glibc, UID 1001 and a clean virtualenv,
  not an identical Ubuntu VM. The import/version failures occur independently of
  the distro, and remote rerun is still required.
- The previous local Linux harness used a cached backend image. Its current
  metadata has Kombu 5.6.2, packaging 26.3 and Billiard 4.3.1; it does not establish
  correctness of a fresh requirements resolution. The fresh reproduction retains
  the remote Billiard 4.3.2/Click 8.5.1 even after the minimal Kombu fix.

## C. Minimal implementation and files

1. `backend/requirements.txt`: explicitly constrain the already-transitive Kombu
   dependency to 5.6.2, with the Redis compatibility reason. CI and production
   images both consume this file, so the fix is not limited to a test-only package.
2. `backend/tests/test_celery_runtime.py`: regression test in a cold subprocess,
   without a broker or application settings. Check Redis transport import and that
   the installed Redis client satisfies both Celery and Kombu Redis-extra metadata.
   No hardcoded expected Kombu pin, network connection or eager-mode substitution.
3. This handoff: evidence, reproduction, validation, boundaries and separate npm
   observations.

No application source, workflow, worker architecture, authentication, migration,
I16 assertion/timeout, broker-down assertion or deployment gate was changed.
No additional source diagnostic logger is needed to guess an exception: the
startup exception was captured and reproduced before changing requirements.

## D. Reproduction and actual commands

The ignored `.cache/fix02-ci-remediation/` contains the disposable harness,
Dockerfiles and sanitized logs. `Dockerfile` creates a fresh virtualenv from the
requirements in a separate test image and runs as UID 1001. The original/fixed
images retain their respective installed requirements; source is mounted read-only.
The base image supplies Python/system libraries, not inherited virtualenv packages.

Fixtures are new labeled PostgreSQL/MinIO/Redis containers with tmpfs, isolated
network and random loopback ports. MinIO uses the already approved immutable
Chainguard digest. No existing SLRMS volume, staging/production endpoint or cloud
credential is mounted or used. The first blank-fixture invocation lacked the vector
extension; applying the same `alembic upgrade head` as CI corrected setup before
the actual startup reproduction. This setup error is not the I16 root cause.

Actual local commands, with only disposable targets configured by the harness:

```powershell
python .cache/fix02-m2/manage.py up
# Build clean baseline virtualenv with original requirements and UID 1001.
python -c "import pathlib,subprocess; pathlib.Path('.cache/fix02-ci-remediation/requirements.txt').write_bytes(subprocess.check_output(['git','show','e54a5ce:backend/requirements.txt']))"
docker build -t slrms-fix02-ci-remediation:diagnostics -f .cache/fix02-ci-remediation/Dockerfile .cache/fix02-ci-remediation
python .cache/fix02-ci-remediation/run_clean.py -m alembic upgrade head
python .cache/fix02-ci-remediation/run_clean.py /diagnostics/repro_capture.py
# PackagingProbe.Dockerfile adds only packaging to the original diagnostic image.
# The packaging-only I16 probe still fails with the Redis version mismatch.
# After copying amended requirements into the ignored build context:
Copy-Item backend/requirements.txt .cache/fix02-ci-remediation/requirements.txt
docker build -t slrms-fix02-ci-remediation:fixed -f .cache/fix02-ci-remediation/Dockerfile .cache/fix02-ci-remediation
$env:CI_REMEDIATION_IMAGE='slrms-fix02-ci-remediation:fixed'
python .cache/fix02-ci-remediation/run_clean.py /diagnostics/repro_capture.py tests.integration.test_celery_redelivery tests.test_celery_runtime
$env:CI_REMEDIATION_UNIT='1'
python .cache/fix02-ci-remediation/run_clean.py /diagnostics/unit_regression.py
Remove-Item Env:CI_REMEDIATION_UNIT
python .cache/fix02-ci-remediation/run_clean.py /diagnostics/repro_capture.py tests.integration.test_storage_reliability tests.integration.test_celery_redelivery tests.integration.test_local_reliability tests.test_storage_cleanup.LocalDeletionContractTestCase
python .cache/fix02-m2/manage.py redis-stop
$env:RUN_BROKER_DOWN_INTEGRATION='1'
python .cache/fix02-ci-remediation/run_clean.py -m unittest tests.integration.test_cleanup_independence -v
python .cache/fix02-m2/manage.py redis-start
python .cache/fix02-ci-remediation/run_clean.py -m ruff check app tests alembic --no-cache
# All 23 production-critical mypy paths from CI, plus tests/test_celery_runtime.py:
# --ignore-missing-imports --check-untyped-defs --explicit-package-bases
# --cache-dir /tmp/remediation-mypy
python .cache/fix02-ci-remediation/run_clean.py -m pip check
```

For an independent Linux runner, provision only new PostgreSQL/MinIO/Redis test
services and export the explicit test environment from `.github/workflows/ci.yml`.
Install requirements-dev in a new virtualenv, migrate its dedicated DB, then run
the same unittest modules with the stated opt-in flags. Never source the local
`.env` or reuse shared databases/buckets. A baseline reproduction must install the
original e54a5ce requirements in a separate environment, not this fixed file.

## E. Validation results

| Check | Actual result | Ignored evidence |
| --- | --- | --- |
| Original I16 in clean Linux | FAIL, same early exit 1; missing packaging | `i16-before.log` |
| Packaging-only real I16 probe | FAIL, Redis VersionMismatch | `i16-packaging-only.log` |
| New regression on original dependencies | FAIL, missing packaging | `runtime-regression-before.log` |
| New regression on packaging-only dependencies | FAIL, unsupported Redis metadata | `runtime-regression-packaging-only.log` |
| Fixed real I16 + new regression | 2 PASS, 0 skips | `i16-after.log` |
| Exact CI reliability group | 27 PASS, 0 skips | `reliability-group.log` |
| Real broker-down independent cleanup | 1 PASS, 0 skips, graceful stop | `broker-down.log` |
| Full Linux backend suite incl. real PG transaction/locking and processing/dispatcher tests | 333 run: 303 PASS, 30 expected opt-in/platform skips; 0 failures/errors | `backend-full.log` |
| Coverage | 83.2947%, 3885 statements / 649 missed; threshold 70 PASS | `backend-full.log` |
| Ruff app/tests/alembic | PASS | `ruff.log` |
| Mypy 23 CI critical paths + new test | PASS, 24 source files | `mypy.log` |
| Fresh fixed virtualenv pip check | PASS | `pip-check.log` |
| New cold-process regression on Windows | 1 PASS | Actual unittest invocation in session |
| Git diff and new-file whitespace | PASS | Final patch audit |
| Remote CI with fix | NOT RUN, no commit/push authorized | Prior run remains failed |
| Operational restore/Caddy and real-backend browser acceptance in this remediation | NOT RUN | Must complete in subsequent remote run |

The 30 main-suite skips are the same as the original CI suite: 28 explicit opt-in
cases plus two Windows handle cases on Linux. The separately required S3 reliability,
Celery and broker-down runs are not counted as passed merely because the main
suite skipped them. I16 assertions still verify a distinct prefork child is killed,
redelivery on a new child with the same task ID, successful document-deleted outcome,
no remaining document/chunks and retained bytes until physical cleanup.

## F. Risk, review and next gate

- Keep the Kombu constraint until a separately tested Celery/Redis/Kombu upgrade.
  Other unconstrained transitive packages remain outside this minimal fix.
- No claim of Python dependency security certification or whole-repository mypy
  cleanliness. The maintained CI paths were checked; unrelated type errors disclosed
  by M3 remain outside scope.
- Review the new cold-process test and evidence for both failure modes. Do not
  replace real I16 with the dependency probe; both must continue to run.
- Review patch: `.cache/fix02-ci-remediation/ci-fix-review.patch`, including tracked
  requirements and both untracked source/test/documentation files. Cache helpers,
  logs, audit JSONs and temporary analysis lockfiles are excluded.
- After approval, create a new fix commit and rerun the full remote workflow.
  Required operational/restore/browser groups must actually execute without skips.
  This handoff authorizes none of those Git/remote actions by itself.
- All production gates remain CLOSED. Owner/Ops approvals, LocalStorage policy
  sign-off, intended-topology I01/I08/I20/I23 rehearsal, target/IAM/certification,
  alert delivery and backup fencing/restore boundaries remain outstanding.


## Separate npm security observations

Read-only audit results; no dependency upgrade/fix was applied to the project. Package presence is not an exploitability proof. No security-scan PASS is claimed.

Audit on 2026-11-09: committed lockfile reports **15** vulnerable packages (7 moderate,
7 high, 1 critical), including **3** in production-only mode (2 high, 1 critical).
The isolated Docker-style manifest resolution reports **11** (6 moderate, 4 high,
1 critical), including **2** in production-only mode (1 high, 1 critical). Audit exit
1 denotes reported vulnerabilities, not a successful security gate. The following
tables retain package paths and 38 package/advisory-ID pairs for separate triage.

### locked dependency paths

| Package / version | Severity | Dependency path | Production relevance |
| --- | --- | --- | --- |
| `@next/eslint-plugin-next@14.2.35` | high | `slrms-frontend (dev) -> eslint-config-next@14.2.35 -> @next/eslint-plugin-next@14.2.35` | Dev/build tooling in this lock; review build exposure |
| `@typescript-eslint/eslint-plugin@8.67.0` | moderate | `slrms-frontend (dev) -> eslint-config-next@14.2.35 -> @typescript-eslint/eslint-plugin@8.67.0` | Dev/build tooling in this lock; review build exposure |
| `@typescript-eslint/parser@8.67.0` | moderate | `slrms-frontend (dev) -> eslint-config-next@14.2.35 -> @typescript-eslint/parser@8.67.0` | Dev/build tooling in this lock; review build exposure |
| `@typescript-eslint/type-utils@8.67.0` | moderate | `slrms-frontend (dev) -> eslint-config-next@14.2.35 -> @typescript-eslint/eslint-plugin@8.67.0 -> @typescript-eslint/type-utils@8.67.0` | Dev/build tooling in this lock; review build exposure |
| `@typescript-eslint/typescript-estree@8.67.0` | moderate | `slrms-frontend (dev) -> eslint-config-next@14.2.35 -> @typescript-eslint/parser@8.67.0 -> @typescript-eslint/typescript-estree@8.67.0` | Dev/build tooling in this lock; review build exposure |
| `@typescript-eslint/utils@8.67.0` | moderate | `slrms-frontend (dev) -> eslint-config-next@14.2.35 -> @typescript-eslint/eslint-plugin@8.67.0 -> @typescript-eslint/utils@8.67.0` | Dev/build tooling in this lock; review build exposure |
| `brace-expansion@5.0.9` | high | `slrms-frontend (dev) -> eslint-config-next@14.2.35 -> @typescript-eslint/parser@8.67.0 -> @typescript-eslint/typescript-estree@8.67.0 -> minimatch@10.2.6 -> brace-expansion@5.0.9` | Dev/build tooling in this lock; review build exposure |
| `brace-expansion@1.1.18` | high | `slrms-frontend (dev) -> eslint@8.57.1 -> minimatch@3.1.5 -> brace-expansion@1.1.18` | Dev/build tooling in this lock; review build exposure |
| `brace-expansion@2.1.4` | high | `slrms-frontend (dev) -> eslint-config-next@14.2.35 -> @next/eslint-plugin-next@14.2.35 -> glob@10.3.10 -> minimatch@9.0.9 -> brace-expansion@2.1.4` | Dev/build tooling in this lock; review build exposure |
| `eslint-config-next@14.2.35` | high | `slrms-frontend (dev) -> eslint-config-next@14.2.35` | Dev/build tooling in this lock; review build exposure |
| `glob@10.3.10` | high | `slrms-frontend (dev) -> eslint-config-next@14.2.35 -> @next/eslint-plugin-next@14.2.35 -> glob@10.3.10` | Dev/build tooling in this lock; review build exposure |
| `js-yaml@4.3.1` | high | `slrms-frontend (dev) -> eslint@8.57.1 -> js-yaml@4.3.1` | Dev/build tooling in this lock; review build exposure |
| `minimatch@10.2.6` | moderate | `slrms-frontend (dev) -> eslint-config-next@14.2.35 -> @typescript-eslint/parser@8.67.0 -> @typescript-eslint/typescript-estree@8.67.0 -> minimatch@10.2.6` | Dev/build tooling in this lock; review build exposure |
| `minimatch@9.0.9` | moderate | `slrms-frontend (dev) -> eslint-config-next@14.2.35 -> @next/eslint-plugin-next@14.2.35 -> glob@10.3.10 -> minimatch@9.0.9` | Dev/build tooling in this lock; review build exposure |
| `next@14.2.35` | critical | `slrms-frontend (prod) -> next@14.2.35` | Included in production-only audit; reachability NOT VERIFIED |
| `postcss@8.4.31` | high | `slrms-frontend (prod) -> next@14.2.35 -> postcss@8.4.31` | Included in production-only audit; reachability NOT VERIFIED |
| `postcss-selector-parser@6.1.4` | moderate | `slrms-frontend (dev) -> tailwindcss@3.4.19 -> postcss-selector-parser@6.1.4` | Dev/build tooling in this lock; review build exposure |
| `source-map-js@1.2.1` | high | `slrms-frontend (prod) -> next@14.2.35 -> postcss@8.4.31 -> source-map-js@1.2.1` | Included in production-only audit; reachability NOT VERIFIED |

### container dependency paths

| Package / version | Severity | Dependency path | Production relevance |
| --- | --- | --- | --- |
| `@next/eslint-plugin-next@14.2.35` | high | `slrms-frontend (dev) -> eslint-config-next@14.2.35 -> @next/eslint-plugin-next@14.2.35` | Dev/build tooling in this lock; review build exposure |
| `@typescript-eslint/eslint-plugin@8.72.1` | moderate | `slrms-frontend (dev) -> eslint-config-next@14.2.35 -> @typescript-eslint/eslint-plugin@8.72.1` | Dev/build tooling in this lock; review build exposure |
| `@typescript-eslint/parser@8.72.1` | moderate | `slrms-frontend (dev) -> eslint-config-next@14.2.35 -> @typescript-eslint/parser@8.72.1` | Dev/build tooling in this lock; review build exposure |
| `@typescript-eslint/type-utils@8.72.1` | moderate | `slrms-frontend (dev) -> eslint-config-next@14.2.35 -> @typescript-eslint/eslint-plugin@8.72.1 -> @typescript-eslint/type-utils@8.72.1` | Dev/build tooling in this lock; review build exposure |
| `@typescript-eslint/typescript-estree@8.72.1` | moderate | `slrms-frontend (dev) -> eslint-config-next@14.2.35 -> @typescript-eslint/parser@8.72.1 -> @typescript-eslint/typescript-estree@8.72.1` | Dev/build tooling in this lock; review build exposure |
| `@typescript-eslint/utils@8.72.1` | moderate | `slrms-frontend (dev) -> eslint-config-next@14.2.35 -> @typescript-eslint/eslint-plugin@8.72.1 -> @typescript-eslint/utils@8.72.1` | Dev/build tooling in this lock; review build exposure |
| `eslint-config-next@14.2.35` | high | `slrms-frontend (dev) -> eslint-config-next@14.2.35` | Dev/build tooling in this lock; review build exposure |
| `glob@10.3.10` | high | `slrms-frontend (dev) -> eslint-config-next@14.2.35 -> @next/eslint-plugin-next@14.2.35 -> glob@10.3.10` | Dev/build tooling in this lock; review build exposure |
| `minimatch@10.2.6` | moderate | `slrms-frontend (dev) -> eslint-config-next@14.2.35 -> @typescript-eslint/parser@8.72.1 -> @typescript-eslint/typescript-estree@8.72.1 -> minimatch@10.2.6` | Dev/build tooling in this lock; review build exposure |
| `minimatch@9.0.9` | moderate | `slrms-frontend (dev) -> eslint-config-next@14.2.35 -> @next/eslint-plugin-next@14.2.35 -> glob@10.3.10 -> minimatch@9.0.9` | Dev/build tooling in this lock; review build exposure |
| `next@14.2.35` | critical | `slrms-frontend (prod) -> next@14.2.35` | Included in production-only audit; reachability NOT VERIFIED |
| `postcss@8.4.31` | high | `slrms-frontend (prod) -> next@14.2.35 -> postcss@8.4.31` | Included in production-only audit; reachability NOT VERIFIED |

### Advisory IDs (both resolutions)

| Package | Advisory | Severity | Affected ranges | Title |
| --- | --- | --- | --- | --- |
| `brace-expansion` | [GHSA-6j4f-fj2g-mc7p](https://github.com/advisories/GHSA-6j4f-fj2g-mc7p) | high | `<1.1.19 ; >=2.0.0 <2.1.5 ; >=4.0.0 <5.0.10` | brace-expansion: DoS via uncontrolled recursion in parseCommaParts causing stack exhaustion |
| `brace-expansion` | [GHSA-q2hr-2g5m-vwhr](https://github.com/advisories/GHSA-q2hr-2g5m-vwhr) | moderate | `<1.1.21 ; >=2.0.0 <2.1.7 ; >=4.0.0 <5.0.12` | brace-expansion: Quadratic-time expansion of the `{a},b}` rewrite causes CPU denial of service |
| `brace-expansion` | [GHSA-qhr7-859c-m2p7](https://github.com/advisories/GHSA-qhr7-859c-m2p7) | high | `<1.1.20 ; >=2.0.0 <2.1.6 ; >=4.0.0 <5.0.11` | brace-expansion: DoS via uncontrolled recursion on nested brace groups causing stack exhaustion |
| `glob` | [GHSA-3g3m-2fjr-6pw4](https://github.com/advisories/GHSA-3g3m-2fjr-6pw4) | moderate | `>=9.0.0 <=14.0.1` | Glob: AbortSignal cancellation bypass allows post-timeout filesystem traversal |
| `glob` | [GHSA-5j98-mcp5-4vw2](https://github.com/advisories/GHSA-5j98-mcp5-4vw2) | high | `>=10.2.0 <10.5.0` | glob CLI: Command injection via -c/--cmd executes matches with shell:true |
| `js-yaml` | [GHSA-2883-xcg3-v3hh](https://github.com/advisories/GHSA-2883-xcg3-v3hh) | high | `>=4.0.0 <4.3.2` | js-yaml: maxTotalMergeKeys does not limit CPU use for empty merge sources |
| `minimatch` | [GHSA-g3hv-75wg-m249](https://github.com/advisories/GHSA-g3hv-75wg-m249) | moderate | `>=7.0.0 <11.0.1` | minimatch has potential denial of service via globparts amplification |
| `next` | [GHSA-2464-fhr4-w9xw](https://github.com/advisories/GHSA-2464-fhr4-w9xw) | critical | `>=10.0.0 <=15.5.27` | Next.js: Unauthenticated Remote Code Execution in Image Optimization API when SVG files are used |
| `next` | [GHSA-2xp9-vwfh-vxw4](https://github.com/advisories/GHSA-2xp9-vwfh-vxw4) | critical | `>=10.0.0 <15.5.24` | Next.js: Unauthenticated Remote Code Execution in Image Optimization API when AVIF files are used |
| `next` | [GHSA-36qx-fr4f-26g5](https://github.com/advisories/GHSA-36qx-fr4f-26g5) | high | `>=12.2.0 <15.5.16` | Next.js has a Middleware / Proxy bypass in Pages Router applications using i18n |
| `next` | [GHSA-3g8h-86w9-wvmq](https://github.com/advisories/GHSA-3g8h-86w9-wvmq) | low | `>=12.2.0 <15.5.16` | Next.js's Middleware / Proxy redirects can be cache-poisoned |
| `next` | [GHSA-3x4c-7xq6-9pq8](https://github.com/advisories/GHSA-3x4c-7xq6-9pq8) | moderate | `>=10.0.0 <15.5.14` | Next.js: Unbounded next/image disk cache growth can exhaust storage |
| `next` | [GHSA-4633-3j49-mh5q](https://github.com/advisories/GHSA-4633-3j49-mh5q) | moderate | `>=13.0.0 <15.5.21` | Next.js: Cache confusion of response bodies for requests with bodies containing invalid UTF-8 byte sequences |
| `next` | [GHSA-4c39-4ccg-62r3](https://github.com/advisories/GHSA-4c39-4ccg-62r3) | moderate | `>=13.0.0 <15.5.21` | Next.js: Unbounded Server Action payload in Edge runtime |
| `next` | [GHSA-68g3-v927-f742](https://github.com/advisories/GHSA-68g3-v927-f742) | moderate | `>=13.0.0 <15.5.21` | Next.js: Cache confusion of response bodies for requests with bodies |
| `next` | [GHSA-89xv-2m56-2m9x](https://github.com/advisories/GHSA-89xv-2m56-2m9x) | high | `>=14.1.1 <15.5.21` | Next.js: Server-Side Request Forgery in Server Actions on custom servers |
| `next` | [GHSA-8h8q-6873-q5fj](https://github.com/advisories/GHSA-8h8q-6873-q5fj) | high | `>=13.0.0 <15.5.16` | Next.js Vulnerable to Denial of Service with Server Components |
| `next` | [GHSA-955p-x3mx-jcvp](https://github.com/advisories/GHSA-955p-x3mx-jcvp) | moderate | `>=13.0.0 <15.5.21` | Next.js: Unauthenticated disclosure of internal Server Function endpoints |
| `next` | [GHSA-9g9p-9gw9-jx7f](https://github.com/advisories/GHSA-9g9p-9gw9-jx7f) | moderate | `>=10.0.0 <15.5.10` | Next.js self-hosted applications vulnerable to DoS via Image Optimizer remotePatterns configuration |
| `next` | [GHSA-c4j6-fc7j-m34r](https://github.com/advisories/GHSA-c4j6-fc7j-m34r) | high | `>=13.4.13 <15.5.16` | Next.js vulnerable to server-side request forgery in applications using WebSocket upgrades |
| `next` | [GHSA-ffhc-5mcf-pf4q](https://github.com/advisories/GHSA-ffhc-5mcf-pf4q) | moderate | `>=13.4.0 <15.5.16` | Next.js vulnerable to cross-site scripting in App Router applications using CSP nonces |
| `next` | [GHSA-ggv3-7p47-pfv8](https://github.com/advisories/GHSA-ggv3-7p47-pfv8) | moderate | `>=9.5.0 <15.5.13` | Next.js: HTTP request smuggling in rewrites |
| `next` | [GHSA-gx5p-jg67-6x7h](https://github.com/advisories/GHSA-gx5p-jg67-6x7h) | moderate | `>=13.0.0 <15.5.16` | Next.js has cross-site scripting in beforeInteractive scripts with untrusted input |
| `next` | [GHSA-h25m-26qc-wcjf](https://github.com/advisories/GHSA-h25m-26qc-wcjf) | high | `>=13.0.0 <15.0.8` | Next.js HTTP request deserialization can lead to DoS when using insecure React Server Components |
| `next` | [GHSA-h64f-5h5j-jqjh](https://github.com/advisories/GHSA-h64f-5h5j-jqjh) | moderate | `>=10.0.0 <15.5.16` | Next.js has a Denial of Service in the Image Optimization API |
| `next` | [GHSA-m99w-x7hq-7vfj](https://github.com/advisories/GHSA-m99w-x7hq-7vfj) | high | `>=13.0.0 <15.5.21` | Next.js: Denial of Service in App Router using Server Actions |
| `next` | [GHSA-p293-qw3h-jr36](https://github.com/advisories/GHSA-p293-qw3h-jr36) | critical | `>=13.4.0 <15.5.24` | Next.js: Unauthenticated Remote Code Execution on windows-hosted servers |
| `next` | [GHSA-p3m5-59mp-jv5r](https://github.com/advisories/GHSA-p3m5-59mp-jv5r) | high | `>=13.0.0 <=15.5.27` | Next.js: Denial of Service in App Router using Server Actions |
| `next` | [GHSA-p9j2-gv94-2wf4](https://github.com/advisories/GHSA-p9j2-gv94-2wf4) | high | `>=12.0.0 <15.5.21` | Next.js: Server-Side Request Forgery in rewrites via attacker-controlled destination hostname |
| `next` | [GHSA-q4gf-8mx6-v5v3](https://github.com/advisories/GHSA-q4gf-8mx6-v5v3) | high | `>=13.0.0 <15.5.15` | Next.js has a Denial of Service with Server Components |
| `next` | [GHSA-vfv6-92ff-j949](https://github.com/advisories/GHSA-vfv6-92ff-j949) | low | `>=13.4.6 <15.5.16` | Next.js vulnerable to cache poisoning via collisions in React Server Component cache-busting |
| `next` | [GHSA-wfc6-r584-vfw7](https://github.com/advisories/GHSA-wfc6-r584-vfw7) | moderate | `>=14.2.0 <15.5.16` | Next.js vulnerable to cache poisoning in React Server Component responses |
| `postcss` | [GHSA-6g55-p6wh-862q](https://github.com/advisories/GHSA-6g55-p6wh-862q) | high | `<=8.5.11` | PostCSS: Arbitrary file read and information disclosure via attacker-controlled sourceMappingURL in CSS comments |
| `postcss` | [GHSA-fxqj-rqcc-2cmp](https://github.com/advisories/GHSA-fxqj-rqcc-2cmp) | moderate | `<=8.5.22` | PostCSS: incomplete fix of GHSA-6g55-p6wh-862q — attacker-controlled sourceMappingURL reads arbitrary .map files when `from` is unset |
| `postcss` | [GHSA-qx2v-qp2m-jg93](https://github.com/advisories/GHSA-qx2v-qp2m-jg93) | moderate | `<8.5.10` | PostCSS has XSS via Unescaped </style> in its CSS Stringify Output |
| `postcss` | [GHSA-r28c-9q8g-f849](https://github.com/advisories/GHSA-r28c-9q8g-f849) | high | `<=8.5.17` | PostCSS: Path Traversal in Previous Source Map Auto-Loading (sourceMappingURL) leads to Arbitrary .map File Disclosure |
| `postcss-selector-parser` | [GHSA-rj75-hqrm-r3gf](https://github.com/advisories/GHSA-rj75-hqrm-r3gf) | moderate | `<6.1.5` | PostCSS: Quadratic complexity in flat selector parsing allows CPU exhaustion |
| `source-map-js` | [GHSA-68fv-2mgg-jv7q](https://github.com/advisories/GHSA-68fv-2mgg-jv7q) | high | `>=1.0.0 <1.2.2` | source-map-js allows event-loop denial of service through indexed source-map section offsets |

`next` is a production dependency used by the App Router/standalone server. Its `postcss`/`source-map-js` descendants are also reported by the production-only lock audit; whether each path is included in the final traced standalone bundle and reachable with untrusted inputs remains NOT VERIFIED. Development-tool dependencies also execute during install/lint/build and are not dismissed as harmless.

`frontend/next.config.js` enables standalone output/StrictMode only; no custom rewrites, image remotePatterns, CSP nonce or Server Actions configuration was found in the inspected source. This does not prove any advisory inapplicable or certify the public image optimization endpoint. No exploitation requests were sent.

The Docker deps stage copies only package.json and runs npm install, whereas the frontend job uses npm ci with the committed lockfile. The isolated manifest-only resolution reproduces the 11-warning container count without changing the project's lockfile. Its temporary lock and both audit JSON sets remain ignored evidence. Changing Docker dependency installation is outside I16 remediation scope.
