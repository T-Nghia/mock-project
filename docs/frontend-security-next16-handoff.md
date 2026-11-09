# Frontend Security — Next.js 16 implementation handoff

Ngày kiểm chứng: 2026-11-09. Trạng thái: **READY FOR INDEPENDENT REVIEW**, có các giới hạn và finding tooling bên dưới. Chưa có phê duyệt merge hoặc rollout. Không stage, commit, push, mở PR, merge hay deploy.

## A. Git baseline và phạm vi

- Worktree riêng: `D:/mock-project/.cache/security-next16`.
- Branch: `fix/frontend-security-next16`; base/HEAD: `d23d939016cc5cd8541d6c4156b4b31ffbb78213`, từ `origin/develop` sau `git fetch origin`.
- Không mang M1/M2/M3 sang branch này. Không sửa file trong `backend/`, migration, processing/Celery, storage, RAG hoặc DELETE policy.
- Worktree Fix 02 tại `D:/mock-project` giữ branch `fix/storage-reliability-cleanup`, HEAD `d8093228037144e63e938fca4369fd397e3caed3`. Tài liệu untracked `docs/fix02-pre-pr-security-triage.md` được giữ nguyên, không nằm trong patch này.
- Patch review: `.cache/frontend-security-next16/security-review.patch`; manifest và SHA256: `.cache/frontend-security-next16/git-audit.json` trong worktree security. Patch gồm cả tracked và untracked source/tests/handoff; không có dependency installation, cache, credentials hoặc build artifacts.

## B. Dependency versions đã chọn và đã chạy

| Thành phần | Trước | Sau, resolved thực tế |
| --- | --- | --- |
| Next.js / eslint-config-next | 14.2.35 | 16.4.5 / 16.4.5 |
| React / react-dom | 18.3.1 | 19.3.1 / 19.3.1, stable |
| @types/react / react-dom | 18.x | 19.3.0 / 19.3.0 |
| Node / npm | Docker Node 20 | 24.22.2 / 11.19.1, Windows và Linux image |
| @types/node | 20.x | 24.19.2 |
| TypeScript | 5.9.3 resolved | 5.9.3, giữ range 5.x hiện hữu |
| ESLint | 8.x | 9.39.5 |
| sharp | Không có trong image cũ đã triage | 0.35.5, có trong image mới |
| PostCSS của Next | 8.4.31 | 8.5.23 trong build dependency tree |
| PostCSS root tooling | 8.5.26 | 8.5.26 |
| source-map-js | 1.2.1 | 1.2.2 |
| brace-expansion | Có nhánh 1.1.12 | 1.1.21 và 5.0.12 |
| postcss-selector-parser | 6.1.4 | 6.1.6 |

Không đổi UI package major hoặc Playwright 1.55.0. Không dùng `latest`/canary làm application target, `--force`, `--legacy-peer-deps`, hoặc `npm audit fix`. Các patch transitive được cập nhật trong ranges hiện hữu bằng `npm update source-map-js brace-expansion postcss-selector-parser --no-fund`.

`npm ci` cuối chạy bằng Node 24.22.2/npm 11.19.1, không có peer conflict; `npm ls --all --json` exit 0. Một warning ERESOLVE trong bước chuyển lockfile ban đầu liên quan React 18 cũ không còn ở fresh install cuối.

**Tooling limitation:** npm đánh dấu ESLint 9.39.5 hết hỗ trợ. Các plugin React/import/jsx-a11y hiện resolved vẫn khai báo peer đến ESLint 9; không ép ESLint 10 bằng override/force. Đây là follow-up cần reviewer/Tech Lead đánh giá, cùng Moderate phía dưới; không phải chứng nhận toàn bộ tooling đã hết rủi ro.

## C. Breaking changes và implementation

1. `next lint` được thay bằng `eslint .`; chuyển `.eslintrc.json` sang `eslint.config.mjs` với toàn bộ `eslint-config-next/core-web-vitals`. Không tắt rule mới để vượt lint, không giảm TypeScript strictness.
2. Bộ React Hooks rules mới phát hiện synchronous state resets trong effects. Các component bị ảnh hưởng reset state có guard khi input/request key thay đổi; fetch effects giữ cancellation và cập nhật từ response. Tree refresh được reset từ event. Không thêm thư viện fetching/state hoặc abstraction chung.
3. Portal/hydration dùng `useSyncExternalStore` với server snapshot `false`; form/dialog reset khi props đổi; dropdown dùng state cho initial focus và nullable ref theo React 19. Chat dùng sequence ID cho optimistic messages, tạo message ngoài state updater để updater thuần.
4. AuthProvider tách việc đọc current user khỏi state updates và bỏ response sau cleanup. API/RBAC/cookie policy giữ nguyên.
5. Real development StrictMode tái hiện hai refresh requests dùng cùng rotating cookie: một 200, một 401, sau đó frontend quay về login. Bootstrap trước đây gọi `doRefresh()` trực tiếp, trong khi recovery sau 401 có single-flight. Hai luồng nay dùng chung single-flight hiện hữu; không đổi endpoint hoặc backend auth. Regression assert đúng một refresh request khi reload, vẫn kiểm tra logout và protected redirect.
6. Next 16 yêu cầu `jsx: react-jsx`; thêm `.next/dev/types/**/*.ts`, giữ `strict: true`. `next-env.d.ts` là references do Next 16 production build sinh, không chứa dev-path cuối.
7. Audit App Router không thấy middleware, route handlers, Server Actions, `next/headers`, synchronous cookies/headers/request props hoặc `next/image` trong application source. Dynamic document route dùng client `useParams`; search/reset-password đã có Suspense cho `useSearchParams`. Không cần đổi API/caching boundary. Turbopack default build PASS, không có custom Webpack config cần port.

Tham chiếu migration: [version-matched Next 16 guide](https://nextjs.org/docs/app/guides/upgrading/version-16), [ESLint migration](https://nextjs.org/docs/app/api-reference/config/eslint). Đã đọc cả guide bundled trong `frontend/node_modules/next/dist/docs/01-app/02-guides/upgrading/version-16.md` khi Next dev tự sinh agent instructions. File `AGENTS.md` tự sinh được chuyển vào cache, không nằm trong implementation patch.

## D. Files changed, runtime hardening và CI

40 source/config/test/handoff paths: 30 modified, một legacy config deleted, chín new files. Danh sách đầy đủ nằm ở appendix cuối tài liệu và manifest; không tính ignored evidence hoặc generated files.

- `images.unoptimized = true`. Direct Next 16 benign optimizer requests trả 404; không dựa vào `dangerouslyAllowSVG: false` hoặc WebP output format để xử lý AVIF/SVG input.
- Caddy APP site deny prefix `/_next/image*` trước reverse proxy. API site không đổi; không mang DELETE maintenance route của Fix 02 vào branch này.
- Production Compose dùng `ports: !override` với `127.0.0.1:3000:3000`, tránh giữ mapping public từ base qua merge. Base Compose local không đổi; staging vẫn `ports: !reset []`.
- Frontend Dockerfile dùng cùng official Node 24 immutable index digest cho cả ba stages, copy manifest + lock và chạy `npm ci`. Runner giữ standalone output, non-root user `node` (UID 1000).
- CI frontend/E2E dùng Node 24.22.2. E2E job build Next production và thực thi 179 UI/security contracts với API fixtures; JSON guard chặn zero collection, skips, unexpected failures và flaky retries; discovery bước cũ vẫn giữ.
- Các jobs có browser installation dùng Ubuntu 24.04 vì Playwright 1.55 không hỗ trợ runner Ubuntu 26.04. Không đổi trigger/environment/deployment logic của staging/post-deploy workflows; không chạy hai workflows dùng shared environment trong lượt này.
- Container CI gắn revision `${{ github.sha }}` và assert frontend host binding loopback. Backend job, Fix 01 tests, coverage và MinIO configuration không đổi.
- Real-backend suite có config/testDir riêng, fail nếu thiếu sandbox marker/loopback URLs. Không thêm skip để báo xanh. Suite này được chạy local bằng harness; **chưa được wire thành remote CI job**.

## E. Next/React/ESLint compatibility

React 19 nullable refs, full core-web-vitals rules, automatic JSX runtime, client/App Router boundaries và development StrictMode đã được kiểm tra theo C và I. Không thêm async server APIs không tồn tại trên baseline. Không nâng UI packages không cần thiết, không thay TS strictness, không đổi browser assertions hoặc Playwright version. Node24 chạy được cả Windows toolchain, Linux build và standalone runtime. ESLint9 được chọn theo peer compatibility thực tế; lifecycle warning vẫn là finding cần disposition.

## F. Docker provenance và runtime inventory

Image local: `slrms-next16-security:review`, Linux/amd64, Alpine/musl.

| Dữ liệu | Giá trị |
| --- | --- |
| Official base | `node:24.22.2-alpine@sha256:a34ab6d7f6f4813f4d0c5469d74685604b962fbdbf5793a7bc7b4998ecb867c8` |
| Base linux/amd64 manifest | `sha256:ec318aabf188af4e5488847eea4b24452650b9917140563e140762526a37f1df` |
| Final local OCI index/ID | `sha256:5e4265e1bbc944b107bac5342efc13cf8386f57cf3a4fda92ef035cc7732af7f` |
| Final linux/amd64 manifest | `sha256:591cf16014bbce945cd6f2d17262d1f5ed2df82ef62cee998483298623d0859e` |
| OCI revision label | `d23d939-dirty-e4ab2f8fa9f80578` |
| Frontend context SHA256 | `e4ab2f8fa9f805785821e3153b97835c85f322010f9085a8d22ab5b22d2700f9` |

Image chưa publish nên không có registry RepoDigest; local digest không phải release image đã ký/phát hành. Revision label mô tả worktree chưa commit, không giả làm một release SHA. Manifest context trong cache ghi rõ danh sách frontend input files.

Docker Hub CDN trả EOF khi pull; mirror Google tải được **cùng official index digest**, sau đó Docker build dùng official `docker.io/library/node` digest đã cache. Không đổi sang unofficial image hoặc tag cũ.

Read-only, network-none inventory của final image xác minh:

- Node 24.22.2; npm 11.19.1; Next 16.4.5; React/react-dom 19.3.1; sharp 0.35.5.
- libvips 8.18.7; libheif 1.23.5; librsvg 2.63.2. Các binary được sharp load thực tế, không chỉ đọc lockfile.
- Không có traced PostCSS/source-map-js file/package trong final `node_modules`; build tree vẫn được kiểm tra riêng ở versions nêu trên. Vendored `next/dist/compiled/source-map` là package khác, không gọi nó là source-map-js.
- `/app` chỉ có `.next`, `node_modules`, `package.json`, `public`, `server.js`; không có `.env`, source tree, lock/build cache thừa tại app root. Base Node image vẫn có npm toolchain.
- 18 versioned package records và 49 vendored package records thiếu version. Official npm bulk advisory lookup cho 18 records trả `{}`; lookup này **không bao phủ hoàn toàn** vendored code hoặc native/OS CVEs.

18 versioned records: `@img/colour@1.1.0`, `@img/sharp-libvips-linuxmusl-x64@1.3.4`, `@img/sharp-linuxmusl-x64@0.35.5`, `@next/env@16.4.5`, `@swc/helpers@0.5.23`, `client-only@0.0.1`, `detect-libc@2.1.2`, `@edge-runtime/cookies@6.0.0`, `@edge-runtime/ponyfill@4.0.0`, `@edge-runtime/primitives@6.0.0`, `react-is@19.3.0-canary-278794d7-20261002`, `regenerator-runtime@0.13.4`, `next@16.4.5`, `react@19.3.1`, `react-dom@19.3.1`, `semver@7.8.5`, `sharp@0.35.5`, `styled-jsx@5.1.6`. `react-is` là bản Next vendored upstream, không phải application React target được tự chọn canary.

## G. Advisory matrix trước/sau

| Advisory | Baseline / affected range | Evidence mới | Disposition |
| --- | --- | --- | --- |
| [GHSA-2464-fhr4-w9xw, SVG RCE](https://github.com/vercel/next.js/security/advisories/GHSA-2464-fhr4-w9xw) | Next 10–15.5.27; 16.x đến 16.4.0. Baseline package affected; image Alpine cũ không chứng minh exploitability glibc. | Next 16.4.5 và actual sharp 0.35.5; advisory patched từ 16.4.1, workaround sharp >=0.35.5. | **PATCHED**, thêm optimizer/ingress mitigation |
| [GHSA-2xp9-vwfh-vxw4, AVIF RCE](https://github.com/vercel/next.js/security/advisories/GHSA-2xp9-vwfh-vxw4) | Next >=10 <15.5.24; 16.x <16.3.3; baseline affected package. | Next 16.4.5 vượt bản vá 16.3.3; actual libheif 1.23.5. Không suy luận từ output format hoặc SVG workaround. | **PATCHED** |
| [GHSA-7qx7-33qx-rqx2, SVG rejection bypass](https://github.com/vercel/next.js/security/advisories/GHSA-7qx7-33qx-rqx2) | 15.0–15.5.28; 16.0–16.4.4. Next 14 ngoài range công bố này. | Patched 16.4.5 đúng advisory; không chỉ dựa vào default `dangerouslyAllowSVG: false`. | **PATCHED** ở target mới |
| [GHSA-pc58-hwjq-p385, response injection/disclosure](https://github.com/vercel/next.js/security/advisories/GHSA-pc58-hwjq-p385) | <=15.5.28 và 16.x <=16.4.4. App không có upstream-passthrough route handler; không khai thác thực tế. | Patched 16.4.5; Caddy optimizer deny không được coi là mitigation cho advisory này. | **PATCHED** |
| [GHSA-f3mh-rxg3-f5g2, Edge cookie exposure](https://github.com/vercel/next.js/security/advisories/GHSA-f3mh-rxg3-f5g2) | 15.0–15.5.28; 16.0–16.4.4. Baseline Next14 ngoài range; không có Edge cookie route. | Patched 16.4.5; cookie auth vẫn do FastAPI xử lý. | **PATCHED** ở target mới |
| [GHSA-g89c-p67h-r497, libheif](https://github.com/strukturag/libheif/security/advisories/GHSA-g89c-p67h-r497) | >=1.22.0 <=1.23.1, patched 1.23.2. | sharp runtime báo heif 1.23.5. | **PATCHED** |
| [GHSA-p293-qw3h-jr36, Windows RCE](https://github.com/vercel/next.js/security/advisories/GHSA-p293-qw3h-jr36) | Baseline package trong affected Next; image production không phải Windows. | Next 16.4.5 vượt bản vá 16.3.3; runtime Linux. | **PATCHED** |
| PostCSS [GHSA-qx2v-qp2m-jg93](https://github.com/advisories/GHSA-qx2v-qp2m-jg93), [GHSA-6g55-p6wh-862q](https://github.com/advisories/GHSA-6g55-p6wh-862q), [GHSA-fxqj-rqcc-2cmp](https://github.com/advisories/GHSA-fxqj-rqcc-2cmp), [GHSA-r28c-9q8g-f849](https://github.com/advisories/GHSA-r28c-9q8g-f849) | Fix thresholds lần lượt 8.5.10 / 8.5.12 / 8.5.23 / 8.5.18; Next14 nested 8.4.31 affected. | Nested 8.5.23 và root 8.5.26; không traced vào final runtime. | **PATCHED** build tree; **NOT APPLICABLE WITH EVIDENCE** cho traced runtime package |
| [GHSA-68fv-2mgg-jv7q, source-map-js](https://github.com/advisories/GHSA-68fv-2mgg-jv7q) | >=1 <1.2.2; baseline 1.2.1. | Lock/install 1.2.2; không traced runtime package. | **PATCHED** build tree |
| brace-expansion advisories; postcss-selector-parser GHSA-rj75-hqrm-r3gf | Các vulnerable resolved versions cũ còn trong lockfile được giữ lại khi chỉ đổi Next. | Semver-compatible refresh: brace 1.1.21/5.0.12, selector 6.1.6. | **PATCHED**, audit không còn báo |
| [GHSA-5j98-mcp5-4vw2](https://github.com/advisories/GHSA-5j98-mcp5-4vw2), [GHSA-3g3m-2fjr-6pw4](https://github.com/advisories/GHSA-3g3m-2fjr-6pw4), glob | Baseline dev glob 10.3.10 và inherited @next/eslint-plugin-next/config-next findings. | New lock không còn package glob; Next16 tooling đổi dependency chain. | **NOT APPLICABLE WITH EVIDENCE** cho dependency tree mới |
| [GHSA-2883-xcg3-v3hh, js-yaml](https://github.com/advisories/GHSA-2883-xcg3-v3hh) | Baseline tooling 4.1.x trước bản vá nhánh 4.x. | Resolved 4.3.2; audit mới không còn báo. | **PATCHED** |
| [GHSA-g3hv-75wg-m249, minimatch ReDoS](https://github.com/advisories/GHSA-g3hv-75wg-m249) | >=7 <11.0.1. | `@typescript-eslint/typescript-estree` vẫn dùng minimatch 10.2.6; chỉ dev tree, không traced runtime. | **UNRESOLVED**, tooling Moderate |

Không gửi payload RCE hoặc exploit vào bất kỳ hệ thống nào. Package patch evidence và reachability probes không phải exploitation verification.

## H. npm audit và remaining findings

Audit cùng thời điểm 2026-11-09, bằng npm 11.19.1:

| Tree | Kết quả thực tế |
| --- | --- |
| Baseline develop committed lock, `npm audit --package-lock-only --json` | 15 = 1 Critical + 7 High + 7 Moderate; exit nonzero |
| Final frontend lock/install, `npm audit --json` | 8 Moderate; 0 High/Critical; exit nonzero |
| Final `npm audit --omit=dev --json` | 0 findings; exit 0 |
| Final `npm ls --all --json` | Exit 0; không invalid/missing peer |
| Versioned records từ final image, official npm advisory bulk endpoint | Không trả advisory; giới hạn nêu ở E |

Tám affected package nodes còn lại là `minimatch`, `@typescript-eslint/eslint-plugin`, `@typescript-eslint/parser`, `@typescript-eslint/type-utils`, `@typescript-eslint/typescript-estree`, `@typescript-eslint/utils`, `typescript-eslint`, `eslint-config-next`. Đây là một advisory gốc ReDoS với bảy inherited nodes, không phải tám lỗ hổng production độc lập. Range minimatch được dependency yêu cầu là 10.x; advisory fix 11.0.1 cần major khác. Không ép override xuyên major. Audit gợi ý downgrade config-next 15.5.29; không áp dụng vì không phù hợp Next16 target.

Các dev findings có thể ảnh hưởng CI xử lý input không tin cậy, nên không tuyên bố security toàn bộ repository PASS. Reviewer/Tech Lead cần disposition riêng cho Moderate và vòng đời ESLint 9. Không chạy OS/native vulnerability scanner; zero npm audit không bao phủ native binaries hay 49 vendored records thiếu version.

## I. Validation results và evidence

| Lệnh/nhóm | Kết quả | Loại bằng chứng |
| --- | --- | --- |
| `npm ci --no-fund` trong frontend, Node24 | **LOCAL PASS**; chạy fresh cả trước và sau transitive updates | Lockfile/peer validation; warning tooling được giữ lại |
| `npm ci --no-audit --no-fund` trong e2e | **LOCAL PASS** | Playwright lock không đổi |
| `npm run lint` | **LOCAL PASS**, Windows và Linux builder container | Toàn bộ flat core-web-vitals config |
| `npm run typecheck` | **LOCAL PASS**, Windows và Linux | Có thêm lần chạy khi di chuyển `.next` ra ngoài và bỏ tsbuildinfo để chứng minh clean-checkout behavior |
| `npm run build` | **LOCAL PASS**, Windows Node24 và Linux Docker | Turbopack; 13 generated pages, document dynamic route |
| `npx playwright test --config playwright.ui.config.js --reporter=json` | **179/179 PASS**, 0 skips/flaky/unexpected | Production frontend; API **fixtures/mocks**, không phải real backend |
| `python e2e/scripts/run-security-local.py --backend-image mock-project-backend:latest --frontend-image slrms-next16-security:review` | **2/2 PASS**, 0 skips/flaky/unexpected | Real develop API + PostgreSQL/pgvector + MinIO + Redis; fake external AI only |
| Lệnh trên thêm `--frontend-mode development` | **2/2 PASS**, 0 skips/flaky/unexpected | Real backend và React19 StrictMode; đúng một refresh request trên reload |
| `docker build --build-arg BUILD_REVISION=... -t slrms-next16-security:review frontend` | **LOCAL PASS** | Final standalone image theo F |
| `docker build --target builder ...`; container `npm run lint` / `npm run typecheck` | **LOCAL PASS** | Linux/musl Node24 toolchain |
| Direct Next benign `/_next/image` / valid local URL params | **404 PASS**, static CSS/JS **200 PASS** | `security-runtime.spec.js`, không có exploit |
| Caddy 2.10.2 actual config, disposable HTTP sandbox | Optimizer/no-query/query/trailing slash **404**; login/static asset **200** | Real Caddy + standalone frontend; không diễn tập public TLS/firewall |
| `docker compose -f ... config --format json` production/staging | **LOCAL PASS** | Production frontend chỉ loopback; staging không publish port frontend; không `up` shared stack |
| `rhysd/actionlint:1.7.12 -shellcheck=` | **LOCAL PASS** | Workflow YAML/schema/actions expressions; standalone shellcheck **NOT RUN** |
| Python fixture/harness AST parse | **LOCAL PASS** | Không import chạy fixture ngoài sandbox |
| `git diff --check`, whitespace new files, reverse-apply patch check | **LOCAL PASS** | Xem manifest audit cho exact files/hashes |
| Remote GitHub Actions | **NOT RUN** | Chưa commit/push theo giới hạn |
| Combined frontend + Fix02 M1/M2/M3 | **NOT RUN / REQUIRED LATER** | Security branch bắt đầu từ develop, không có Fix02 routes/fixtures |

179 UI cases gồm admin 7, app-shell 17, auth 9, bookmarks 6, dashboard 28, library 16, upload 25, workspace/chat 18, folders 9, responsive 43, benign security endpoint 1. Chưa có unit/component framework riêng trên baseline; các interactions/keyboard/focus được kiểm chứng qua browser contracts, không gọi chúng là unit tests.

Real harness dùng backend source mount **read-only từ branch develop này**, migrations đến `e5f6a7b8c9d0`; không import M1/M2/M3. Test tooling image cached có FastAPI 0.111.0, SQLAlchemy 2.0.30, psycopg2 2.9.9, pgvector 0.2.5, boto3 1.40.21, Celery 5.4.0, Redis 5.0.4, Kombu 5.6.2. Không coi đây là fresh backend release image; không kiểm chứng lại Celery I16 trong frontend remediation.

Các lần harness ban đầu FAIL được ghi nhận: mount tmpfs vào source read-only; Docker Desktop internal-network không forward port; thiếu Redis cho health/ready; email `.test` bị EmailStr từ chối; test chưa chờ navigation/tab đúng; kỳ vọng filename khác contract CORS hiện hữu; development submit trước hydration. Các lỗi này được sửa ở harness/test, không giảm assertions/timeout. StrictMode race được sửa ở frontend single-flight và kiểm chứng lại. Download vẫn giữ fallback browser filename `document.txt` của baseline; byte content được so sánh chính xác với tệp upload.

Evidence local (ignored):

- Cache worktree: `.cache/frontend-security-next16/{docker-build.log,frontend-context.json,image-inspect.json,runtime-inventory.json,runtime-audit.json,caddy-probes.json}`.
- Real suite: `.cache/frontend-security-next16/real-backend/{playwright.json,cleanup.json,*-backend.log}`; dev suite tại `real-backend-development/`.
- Audit/UI JSON: `D:/mock-project/.cache/frontend-security-next16-planning/{audit-final.json,audit-prod.json,dependency-tree.json,browser-ui-final.json}`; baseline tại `baseline-audit/audit.json`.
- Mỗi production run dọn 5 containers và network riêng; development run dọn 4 containers/network và process tree Next dev của harness. Không xóa cached images hoặc volumes cũ. Test credentials được sinh riêng, không xuất ra handoff/patch.

### I.1. Cách tái hiện an toàn

Chạy từ worktree security, Node 24.22.2/npm 11.19.1:

```powershell
cd frontend
npm ci --no-fund
npm run lint
npm run typecheck
npm run build
cd ../e2e
npm ci --no-audit --no-fund
npx playwright install chromium
$env:APP_URL = 'http://127.0.0.1:3000'
npx playwright test --config playwright.ui.config.js
cd ..
docker build --build-arg BUILD_REVISION=uncommitted-review -t slrms-next16-security:review frontend
# Có thể build backend tooling mới từ develop; local evidence đã dùng cached
# mock-project-backend:latest chỉ như Python dependency environment.
docker build -t slrms-security-backend:local backend
python e2e/scripts/run-security-local.py --backend-image slrms-security-backend:local --frontend-image slrms-next16-security:review
python e2e/scripts/run-security-local.py --backend-image slrms-security-backend:local --frontend-image slrms-next16-security:review --frontend-mode development
```

Không chạy shared staging lifecycle suite để thay thế sandbox. Harness yêu cầu ports 3000/8000 đang trống, tạo network/bucket/container riêng; PostgreSQL/MinIO/Redis dùng tmpfs, chỉ API/frontend publish loopback. AI providers được thay trong test bootstrap, không đổi backend source hoặc gọi LLM thật. Cleanup kiểm tra ownership labels trước khi remove. Đây là dedicated bridge network, không phải bảo đảm egress bị firewall chặn.

## J. Combined Fix 02 integration và merge risks

1. Chưa chạy I01–I24 hoặc browser orphan-chat acceptance trên tổ hợp security + M1/M2/M3. Cần sync sau các quyết định merge được phê duyệt và chạy lại trên đúng combined release-candidate SHA.
2. `frontend/components/chat/chat-panel.tsx`, auth/UI effects, CI và Caddy có thể conflict với Fix02. Preserve orphan sessions, citation snapshots, null document IDs, 409 new-message policy, independent worker, no-skip reliability/browser guards và production DELETE restrictions.
3. Khi kết hợp Caddy, retain API DELETE maintenance protection của Fix02 và APP optimizer deny của security branch. Không dùng một phía để ghi đè phía còn lại.
4. Không dùng CI từ develop này thay wholesale cho CI M3. Node24/Ubuntu24/browser contract additions phải kết hợp với PostgreSQL/MinIO/I16/reliability/operational coverage hiện hữu của Fix02.

## K. Remaining gates

- Independent review của implementation và single-flight/effect guards; Tech Lead disposition cho 8 tooling Moderate + ESLint9 support lifecycle.
- Remote CI trên security branch sau khi được phép commit/push; local PASS không đại diện remote PASS.
- Supply-chain/OS/native scan và release image signing/provenance theo quy trình Ops; 49 vendored records thiếu version chưa được audit độc lập.
- Intended-topology HTTPS/ingress/firewall rehearsal; chỉ Compose config và sandbox Caddy được xác minh local.
- Không có production access hoặc exploitability test. Owner/Ops vẫn phải phê duyệt LocalStorage policy, S3/IAM/certification, monitoring/alert delivery, backup fencing và I01/I08/I20/I23 rehearsal của Fix02.
- Mọi production DELETE/cleanup gates vẫn CLOSED. Không tự certify bucket, đổi IAM, mở PR hoặc rollout.

## L. Review handoff

**READY FOR INDEPENDENT REVIEW**, không đồng nghĩa merge-ready/production-ready. Các Critical được nhắm tới có patch/version/runtime evidence; dev findings và các gate ở K vẫn mở cho disposition.

Reviewer ưu tiên: exact dependency/lockfile peer compatibility; single-flight refresh dưới StrictMode; conditional state resets/cancellation; dropdown focus và dialog hydration; immutable Docker/npm-ci/standalone tracing; optimizer deny và Compose merge semantics; phân biệt mocked UI evidence với real PG/S3/backend evidence; giữ Fix02 invariants khi integration sau này.

Danh sách file chính xác và blob hashes nằm trong review manifest; index phải tiếp tục rỗng. Không có commit mới trong lượt này.

## Appendix: reviewed paths

- `.github/workflows/ci.yml`
- `.github/workflows/post-deploy-smoke.yml`
- `.github/workflows/staging-e2e.yml`
- `deploy/staging/Caddyfile`
- `docker-compose.prod.yml`
- `docs/frontend-security-next16-handoff.md`
- `e2e/fixtures/security_backend.py`
- `e2e/playwright.real.config.js`
- `e2e/playwright.ui.config.js`
- `e2e/scripts/run-security-local.py`
- `e2e/security/security-real-backend.spec.js`
- `e2e/tests/security-runtime.spec.js`
- `frontend/.dockerignore`
- `frontend/.eslintrc.json`
- `frontend/.nvmrc`
- `frontend/Dockerfile`
- `frontend/app/(app)/admin/users/page.tsx`
- `frontend/app/(app)/bookmarks/page.tsx`
- `frontend/app/(app)/dashboard/page.tsx`
- `frontend/app/(app)/documents/[id]/page.tsx`
- `frontend/app/(app)/folders/page.tsx`
- `frontend/app/(app)/search/page.tsx`
- `frontend/components/admin/create-teacher-dialog.tsx`
- `frontend/components/chat/chat-panel.tsx`
- `frontend/components/documents/comments-section.tsx`
- `frontend/components/documents/document-viewer.tsx`
- `frontend/components/documents/use-owned-folders.ts`
- `frontend/components/folders/folder-form-dialog.tsx`
- `frontend/components/layout/app-shell.tsx`
- `frontend/components/ui/confirm-action-dialog.tsx`
- `frontend/components/ui/dialog.tsx`
- `frontend/components/ui/dropdown-menu.tsx`
- `frontend/eslint.config.mjs`
- `frontend/lib/api.ts`
- `frontend/lib/auth-context.tsx`
- `frontend/next-env.d.ts`
- `frontend/next.config.js`
- `frontend/package-lock.json`
- `frontend/package.json`
- `frontend/tsconfig.json`
