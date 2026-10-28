const { test: base, expect } = require("@playwright/test");
const ids = { user: "20000000-0000-4000-8000-000000000001", other: "20000000-0000-4000-8000-000000000002", root: "10000000-0000-4000-8000-000000000001", child: "10000000-0000-4000-8000-000000000002", doc: "30000000-0000-4000-8000-000000000001" };
const date = "2026-10-28T08:00:00Z";
const test = base.extend({
  mock: async ({ page }, use) => {
    const errors = []; page.on("pageerror", (error) => errors.push(error.message));
    const states = [];
    await use(async (options = {}) => { const state = await mockRemaining(page, options); states.push(state); return state; });
    for (const state of states) { for (const release of state.releases) release(); expect(state.unexpected).toEqual([]); }
    expect(errors).toEqual([]);
  },
});

async function mockRemaining(page, options) {
  const role = options.role || "teacher";
  const user = { id: ids.user, full_name: "Nguyễn Minh Anh", email: "minhanh@example.com", role, is_active: true, created_at: date };
  const folder = (id, name, parent = null) => ({ id, name, parent_folder_id: parent, subject: "Trí tuệ nhân tạo", owner_id: ids.user, created_at: date });
  const state = {
    user, authenticated: !options.public, calls: [], unexpected: [], failures: {}, gates: {}, releases: [],
    users: options.empty ? [] : [user, { ...user, id: ids.other, full_name: "Trần Bảo Ngọc", email: "baongoc@example.com", role: "student" }],
    folders: options.empty ? [] : [folder(ids.root, "Nghiên cứu AI"), folder(ids.child, "Học máy", ids.root)],
    documents: [{ id: ids.doc, title: "Nền tảng học máy và ứng dụng", file_path: "documents/example.txt", file_type: "txt", folder_id: ids.root, uploaded_by: ids.user, summary: null, processing_status: "done", created_at: date }],
    bookmarks: options.empty ? [] : Array.from({ length: options.bookmarkCount || 2 }, (_, i) => ({ id: i ? `30000000-0000-4000-8000-${String(i + 1).padStart(12, "0")}` : ids.doc, title: i ? `Tài liệu đã lưu ${i + 1}` : "Nền tảng học máy và ứng dụng", file_type: "txt", processing_status: "done", bookmarked_at: date })),
  };
  state.pause = (key) => { let release; state.gates[key] = new Promise((resolve) => { release = resolve; }); state.releases.push(release); return () => { delete state.gates[key]; release(); }; };
  const tree = (parent = null) => state.folders.filter((f) => f.parent_folder_id === parent).map((f) => ({ ...f, children: tree(f.id) }));
  await page.route("http://localhost:8000/**", async (route) => {
    const request = route.request(); const url = new URL(request.url()); const path = url.pathname; const method = request.method();
    const headers = { "access-control-allow-origin": new URL(process.env.APP_URL).origin, "access-control-allow-credentials": "true", "access-control-allow-headers": "authorization, content-type", "access-control-allow-methods": "GET, POST, PATCH, DELETE, OPTIONS" };
    const respond = (data, status = 200) => route.fulfill({ status, headers, contentType: "application/json", body: JSON.stringify(data) });
    if (method === "OPTIONS") return route.fulfill({ status: 204, headers });
    const body = request.postData() ? request.postDataJSON() : null; const key = `${method} ${path}`;
    state.calls.push({ path, method, body, query: Object.fromEntries(url.searchParams) });
    if (state.gates[key]) await state.gates[key];
    if (state.failures[key]) return respond({ detail: state.failures[key] >= 500 ? "Internal diagnostic should not be displayed on auth forms" : "Yêu cầu chưa được chấp nhận" }, state.failures[key]);
    if (path === "/auth/refresh") return state.authenticated ? respond({ access_token: "remaining-test", token_type: "bearer" }) : respond({ detail: "Refresh cookie khong ton tai" }, 401);
    if (path === "/auth/login") { state.authenticated = true; return respond({ access_token: "remaining-login", token_type: "bearer" }); }
    if (path === "/auth/me") return state.authenticated ? respond(user) : respond({ detail: "Unauthorized" }, 401);
    if (path === "/auth/register") return respond({ ...user, full_name: body.full_name, email: body.email, role: "student" }, 201);
    if (path === "/auth/forgot-password") return respond({ Message: "Neu email ton tai trong he thong, huong dan dat lai mat khau da duoc gui." }, 202);
    if (path === "/auth/reset-password") return respond({ Message: "Dat lai mat khau thanh cong." });
    if (path.startsWith("/auth/admin/")) {
      if (role !== "admin") return respond({ detail: "Forbidden" }, 403);
      if (path === "/auth/admin/users" && method === "GET") return respond(state.users);
      if (path === "/auth/admin/teachers") {
        const created = { ...user, id: "20000000-0000-4000-8000-000000000003", full_name: body.full_name, email: body.email, role: "teacher" };
        state.users.push(created); return respond(created, 201);
      }
      const target = state.users.find((u) => u.id === path.split("/")[4]);
      if (target) { Object.assign(target, body); return respond(target); }
    }
    if (path.startsWith("/folders")) {
      if (role !== "teacher") return respond({ detail: "Khong co quyen truy cap" }, 403);
      if (path === "/folders/tree") return respond(tree());
      if (path === "/folders" && method === "GET") return respond(state.folders);
      if (path === "/folders" && method === "POST") {
        const parent = state.folders.find((f) => f.id === body.parent_folder_id);
        const created = folder(`10000000-0000-4000-8000-${String(state.folders.length + 10).padStart(12, "0")}`, body.name, body.parent_folder_id);
        created.subject = parent?.subject || body.subject || body.name; state.folders.push(created); return respond(created, 201);
      }
      if (path.startsWith("/folders/documents/")) { const doc = state.documents.find((d) => d.id === path.split("/")[3]); Object.assign(doc, body); return respond(doc); }
      const id = path.split("/")[2]; const target = state.folders.find((f) => f.id === id);
      if (target && path.endsWith("/documents")) return respond(state.documents.filter((d) => d.folder_id === id));
      if (target && method === "PATCH") { Object.assign(target, body); return respond(target); }
      if (target && method === "DELETE") {
        const removed = new Set([id]); let size;
        do { size = removed.size; state.folders.forEach((f) => { if (removed.has(f.parent_folder_id)) removed.add(f.id); }); } while (removed.size !== size);
        state.folders = state.folders.filter((f) => !removed.has(f.id)); state.documents.forEach((d) => { if (removed.has(d.folder_id)) d.folder_id = null; });
        return route.fulfill({ status: 204, headers });
      }
    }
    if (path === "/me/bookmarks") { const p = Number(url.searchParams.get("page") || 1); const size = Number(url.searchParams.get("page_size") || 20); return respond({ items: state.bookmarks.slice((p - 1) * size, p * size), total: state.bookmarks.length, page: p, page_size: size }); }
    if (path.endsWith("/bookmark")) {
      const id = path.split("/")[2]; if (method === "DELETE") state.bookmarks = state.bookmarks.filter((doc) => doc.id !== id);
      return respond({ document_id: id, bookmarked: state.bookmarks.some((doc) => doc.id === id) });
    }
    if (path === `/documents/${ids.doc}`) { const { file_path, ...metadata } = state.documents[0]; return respond({ ...metadata, processing_status: "pending", file_size: 512, uploaded_by: { id: user.id, full_name: user.full_name }, tags: [], suggested_questions: [], processing_attempts: 0, processing_started_at: null, processing_completed_at: null, processing_last_error: null }); }
    if (path.endsWith("/view")) return route.fulfill({ headers, contentType: "text/plain", body: "Tài liệu nghiên cứu" });
    if (path.endsWith("/rating")) return respond({ document_id: ids.doc, average: null, count: 0, my_score: null });
    if (path.endsWith("/comments")) return respond({ items: [], total: 0, page: 1, page_size: 50 });
    if (path === "/dashboard") return role === "student" ? respond({ detail: "Forbidden" }, 403) : respond({ role, summary: { total_documents: 0, total_users: role === "admin" ? state.users.length : null }, charts: { uploads_by_day: [], documents_by_folder: [] } });
    state.unexpected.push(key); return respond({ detail: "Unexpected route" }, 404);
  });
  return state;
}
async function fits(page) { expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true); const main = page.getByRole("main"); expect(await main.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true); }
module.exports = { test, expect, ids, fits };
