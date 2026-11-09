const { test: base, expect } = require("@playwright/test");
const date = "2026-11-04T08:00:00Z";
const orphan = { id: "orphan-1", document_id: null, title: "Lịch sử tài liệu đã xóa", created_at: date };
const active = { id: "active-1", document_id: "doc-1", title: "Cuộc trò chuyện đang dùng", created_at: date };
const quote = "Bản trích dẫn được giữ sau khi tài liệu gốc bị xóa.";
const messages = [
  { id: "q1", role: "user", content: "Tóm tắt tài liệu giúp tôi.", sources: [], created_at: date },
  { id: "a1", role: "assistant", content: "Đây là câu trả lời đã lưu.", created_at: date, sources: [{ chunk_id: "deleted-chunk", chunk_index: 0, quote, score: 0.9, heading_path: ["Phần đã lưu"] }] },
];

const test = base.extend({
  history: async ({ page }, use) => {
    const state = { user: { id: "user-1", role: "student", full_name: "Người dùng thử", email: "test@example.com", is_active: true, created_at: date }, sessions: [{ ...orphan }, { ...active }], calls: [], unexpected: [], failures: {}, gates: {}, releases: [] };
    const pageErrors = [];
    page.on("pageerror", (error) => pageErrors.push(error.message));
    state.pause = (key) => { let release; state.gates[key] = new Promise((resolve) => { release = resolve; }); state.releases.push(release); return () => { delete state.gates[key]; release(); }; };
    await page.route("http://localhost:8000/**", async (route) => {
      const request = route.request(); const url = new URL(request.url()); const path = url.pathname; const method = request.method(); const key = `${method} ${path}`;
      const headers = { "access-control-allow-origin": new URL(process.env.APP_URL).origin, "access-control-allow-credentials": "true", "access-control-allow-headers": "authorization, content-type", "access-control-allow-methods": "GET, POST, DELETE, OPTIONS" };
      const respond = (data, status = 200) => route.fulfill({ status, headers, contentType: "application/json", body: JSON.stringify(data) });
      if (method === "OPTIONS") return route.fulfill({ status: 204, headers });
      state.calls.push({ path, method, query: Object.fromEntries(url.searchParams) });
      if (state.gates[key]) await state.gates[key];
      if (state.failures[key]) return respond({ detail: state.failures[key] === 403 ? "Bạn không có quyền xem cuộc trò chuyện này." : "Không tải được dữ liệu thử." }, state.failures[key]);
      if (path === "/auth/refresh") return respond({ access_token: "chat-history-test", token_type: "bearer" });
      if (path === "/auth/me") return respond(state.user);
      if (path === "/chat/sessions" && method === "GET") {
        const limit = Number(url.searchParams.get("limit")); const offset = Number(url.searchParams.get("offset"));
        return respond({ items: state.sessions.slice(offset, offset + limit), total: state.sessions.length, limit, offset });
      }
      const match = path.match(/^\/chat\/sessions\/([^/]+)$/);
      if (match) {
        const session = state.sessions.find((item) => item.id === match[1]);
        if (!session) return respond({ detail: "Không tìm thấy cuộc trò chuyện." }, 404);
        if (method === "DELETE") { state.sessions = state.sessions.filter((item) => item.id !== session.id); return route.fulfill({ status: 204, headers }); }
        if (method === "GET") return respond({ ...session, messages });
      }
      state.unexpected.push(key);
      return respond({ detail: "Unexpected chat history test request" }, 404);
    });
    await use(state);
    for (const release of state.releases) release();
    expect(state.unexpected).toEqual([]);
    expect(pageErrors).toEqual([]);
  },
});
test.use({ channel: process.env.UI_BROWSER_CHANNEL || undefined, video: "off" });

for (const role of ["student", "teacher", "admin"]) test(role + " can reach independent chat history and open an orphan transcript", async ({ page, history }) => {
  history.user.role = role;
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/chat");
  await expect(page.getByRole("navigation", { name: "Điều hướng chính" }).getByRole("link", { name: "Lịch sử trò chuyện" })).toHaveAttribute("aria-current", "page");
  await expect(page.getByRole("main").getByRole("listitem")).toHaveCount(2);
  await page.getByRole("link", { name: orphan.title, exact: true }).click();
  await expect(page.getByRole("main").getByRole("heading", { name: orphan.title, exact: true })).toBeVisible();
  await expect(page.getByRole("status")).toContainText("Cuộc trò chuyện này chỉ đọc");
  await expect(page.getByText(messages[1].content, { exact: true })).toBeVisible();
  await page.getByText("[1] Phần đã lưu", { exact: true }).click();
  await expect(page.getByText(quote, { exact: true })).toBeVisible();
  await expect(page.getByRole("main").locator('a[href^="/documents/"], a[href*="/chunks/"]')).toHaveCount(0);
  await expect(page.locator("textarea")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Gửi câu hỏi" })).toHaveCount(0);
  expect(history.calls.filter((call) => call.path.startsWith("/documents/") || call.method === "POST" && call.path.startsWith("/chat/"))).toHaveLength(0);
});

test("history requests pagination and returns to previous page after deleting its last item", async ({ page, history }) => {
  history.sessions = Array.from({ length: 21 }, (_, i) => ({ ...orphan, id: `s${i}`, title: `Cuộc trò chuyện ${i + 1}` }));
  await page.goto("/chat");
  await expect(page.getByRole("main").getByRole("listitem")).toHaveCount(20);
  await page.getByRole("button", { name: "Tiếp theo", exact: true }).click();
  await expect(page.getByText("Trang 2/2", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Xóa cuộc trò chuyện Cuộc trò chuyện 21", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Xóa cuộc trò chuyện", exact: true }).click();
  await expect(page.getByText("Trang 1/1", { exact: true })).toBeVisible();
  expect(history.calls.some((call) => call.query.offset === "20" && call.query.limit === "20")).toBe(true);
});

test("history shows loading, error retry and empty states", async ({ page, history }) => {
  history.sessions = []; const release = history.pause("GET /chat/sessions");
  await page.goto("/chat");
  await expect(page.getByRole("status", { name: "Đang tải lịch sử trò chuyện" })).toBeVisible();
  history.failures["GET /chat/sessions"] = 503; release();
  await expect(page.getByRole("heading", { name: "Không tải được lịch sử trò chuyện" })).toBeVisible();
  delete history.failures["GET /chat/sessions"];
  await page.getByRole("button", { name: "Thử lại", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Chưa có cuộc trò chuyện nào" })).toBeVisible();
});

test("session deletion confirms, retains transcript on failure, and navigates after success", async ({ page, history }) => {
  await page.goto("/chat/orphan-1");
  await page.getByRole("button", { name: "Xóa cuộc trò chuyện", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Huỷ", exact: true }).click();
  expect(history.calls.filter((call) => call.method === "DELETE")).toHaveLength(0);
  history.failures["DELETE /chat/sessions/orphan-1"] = 503;
  await page.getByRole("button", { name: "Xóa cuộc trò chuyện", exact: true }).click();
  const confirm = page.getByRole("dialog").getByRole("button", { name: "Xóa cuộc trò chuyện", exact: true });
  await confirm.click();
  await expect(page.getByRole("dialog").getByRole("alert")).toContainText("Không thể hoàn tất thao tác. Vui lòng thử lại.");
  await expect(page.getByText(messages[1].content, { exact: true })).toBeVisible();
  delete history.failures["DELETE /chat/sessions/orphan-1"];
  const release = history.pause("DELETE /chat/sessions/orphan-1");
  await confirm.evaluate((button) => { button.click(); button.click(); });
  await expect(confirm).toBeDisabled(); release();
  await expect(page).toHaveURL(/\/chat$/);
  await expect(page.getByRole("link", { name: orphan.title, exact: true })).toHaveCount(0);
  expect(history.calls.filter((call) => call.method === "DELETE")).toHaveLength(2);
});

test("live transcript offers its document workspace", async ({ page, history }) => {
  await page.goto("/chat/active-1");
  await expect(page.getByRole("link", { name: "Mở tài liệu để tiếp tục trò chuyện" })).toHaveAttribute("href", "/documents/doc-1");
});

test("transcript retries loading failures and hides private content after forbidden response", async ({ page, history }) => {
  const release = history.pause("GET /chat/sessions/orphan-1");
  await page.goto("/chat/orphan-1");
  await expect(page.getByRole("status", { name: "Đang tải cuộc trò chuyện" })).toBeVisible();
  history.failures["GET /chat/sessions/orphan-1"] = 503; release();
  await expect(page.getByRole("heading", { name: "Không tải được cuộc trò chuyện" })).toBeVisible();
  delete history.failures["GET /chat/sessions/orphan-1"];
  await page.getByRole("button", { name: "Thử lại", exact: true }).click();
  await expect(page.getByText(messages[1].content, { exact: true })).toBeVisible();
  history.failures["GET /chat/sessions/orphan-1"] = 403;
  await page.reload();
  await expect(page.getByRole("main").getByRole("alert")).toContainText("Bạn không có quyền xem cuộc trò chuyện này.");
  await expect(page.getByText(messages[1].content, { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Xóa cuộc trò chuyện", exact: true })).toHaveCount(0);
});

for (const width of [320, 768, 1440]) test("history and orphan transcript support keyboard and fit width " + width, async ({ page, history }) => {
  history.sessions[0].title = "TenCuocTroChuyen".repeat(20);
  await page.setViewportSize({ width, height: 900 });
  await page.goto("/chat");
  const link = page.getByRole("link", { name: history.sessions[0].title, exact: true });
  await link.focus(); await expect(link).toBeFocused();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.keyboard.press("Enter");
  await expect(page.getByRole("main").getByRole("heading", { name: history.sessions[0].title, exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
