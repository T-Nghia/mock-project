const { test, expect } = require("@playwright/test");

test.use({ channel: process.env.UI_BROWSER_CHANNEL || undefined, video: "off" });

function dashboardPayload(role, { empty = false, noRecent = false, optionalMissing = false, longData = false } = {}) {
  const admin = role === "admin";
  const counts = empty || noRecent ? [0, 0, 0, 0, 0, 0, 0] : [2, 0, 5, 1, 3, 0, 4];
  return {
    role,
    summary: { total_documents: empty ? 0 : longData ? 1234567 : admin ? 128 : 27, ...(admin && !optionalMissing ? { total_users: empty ? 0 : 42 } : {}) },
    charts: {
      uploads_by_day: counts.map((count, index) => ({ date: `2026-10-${21 + index}`, count })),
      documents_by_folder: empty ? [] : [
        { label: longData ? "NghienCuu".repeat(32) : "Học máy", count: admin ? 62 : 12 },
        { label: "Uncategorized", count: admin ? 27 : 6 },
        { label: "Xử lý ngôn ngữ tự nhiên", count: admin ? 39 : 9 },
      ],
      ...(admin && !optionalMissing ? { users_by_role: empty ? [] : [{ label: "admin", count: 1 }, { label: "student", count: 29 }, { label: "teacher", count: 12 }] } : {}),
    },
  };
}

async function mockDashboard(page, options = {}) {
  const role = options.role || "teacher";
  const user = { id: "user-1", role, full_name: options.longData ? "Nguyễn Thị Minh Anh — Nhóm nghiên cứu mô hình ngôn ngữ và tài nguyên học tập" : "Nguyễn Minh Anh", email: "minhanh@slrms.example", is_active: true, created_at: "2026-01-12T08:00:00Z" };
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  const state = { requests: [], status: options.status || 200, hold: options.hold || false, release, payload: dashboardPayload(role, options), unexpected: [] };
  await page.route("http://localhost:8000/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const headers = { "access-control-allow-origin": new URL(process.env.APP_URL).origin, "access-control-allow-credentials": "true", "access-control-allow-headers": "authorization, content-type", "access-control-allow-methods": "GET, POST, OPTIONS" };
    const respond = (body, status = 200) => route.fulfill({ status, headers, contentType: "application/json", body: JSON.stringify(body) });
    if (request.method() === "OPTIONS") return route.fulfill({ status: 204, headers });
    state.requests.push(path);
    if (path === "/auth/refresh") return respond({ access_token: "dashboard-ui-test", token_type: "bearer" });
    if (path === "/auth/me") return respond(user);
    if (path === "/dashboard") {
      if (role === "student") return respond({ detail: "Dashboard is not available for students." }, 403);
      if (state.hold) await gate;
      if (state.status !== 200) return respond({ detail: "Dashboard unavailable" }, state.status);
      return respond(state.payload);
    }
    if (path === "/search") return respond({ items: [], total: 0, page: 1, page_size: 10, total_pages: 1 });
    if (path === "/me/bookmarks") return respond({ items: [], total: 0, page: 1, page_size: 20 });
    if (path === "/folders/tree") return respond([]);
    if (path === "/admin/users") return respond([]);
    state.unexpected.push(path);
    return respond({ detail: "Unexpected test request" }, 404);
  });
  return state;
}

async function openDashboard(page, options = {}) {
  await page.setViewportSize({ width: options.width || 1440, height: 1000 });
  const state = await mockDashboard(page, options);
  await page.goto("/dashboard");
  await expect(page.getByRole("heading", { name: /Chào mừng/ })).toBeVisible();
  return state;
}

async function waitForMetrics(page) {
  await expect(page.getByRole("group", { name: "Tổng số tài liệu", exact: true })).toBeVisible();
}

async function assertNoOverflow(page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  expect(await page.getByRole("main").evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);
}

let pageErrors;
test.beforeEach(async ({ page }) => { pageErrors = []; page.on("pageerror", (error) => pageErrors.push(error.message)); });
test.afterEach(() => expect(pageErrors).toEqual([]));

for (const role of ["student", "teacher", "admin"]) {
  test(role + " dashboard respects API scope, metrics and quick-action permissions", async ({ page }) => {
    const state = await openDashboard(page, { role });
    const main = page.getByRole("main");
    const quick = page.getByRole("navigation", { name: "Truy cập nhanh" });
    await expect(quick.getByRole("link")).toHaveCount(role === "student" ? 2 : role === "teacher" ? 4 : 5);
    await expect(quick.getByRole("link", { name: /^Thư viện tài liệu/ })).toHaveAttribute("href", "/search");
    await expect(quick.getByRole("link", { name: /^Tài liệu đã lưu/ })).toHaveAttribute("href", "/bookmarks");
    await expect(quick.getByRole("link", { name: /^Thư mục/ })).toHaveCount(role === "student" ? 0 : 1);
    await expect(quick.getByRole("link", { name: /^Tải tài liệu lên/ })).toHaveCount(role === "student" ? 0 : 1);
    await expect(quick.getByRole("link", { name: /^Quản lý người dùng/ })).toHaveCount(role === "admin" ? 1 : 0);
    if (role !== "student") {
      await expect(quick.getByRole("link", { name: /^Thư mục/ })).toHaveAttribute("href", "/folders");
      await expect(quick.getByRole("link", { name: /^Tải tài liệu lên/ })).toHaveAttribute("href", "/documents/upload");
    }
    if (role === "admin") await expect(quick.getByRole("link", { name: /^Quản lý người dùng/ })).toHaveAttribute("href", "/admin/users");
    if (role === "student") {
      await expect(page.getByRole("heading", { name: "Bắt đầu từ một tài liệu" })).toBeVisible();
      await expect(main.getByRole("group")).toHaveCount(0);
      expect(state.requests.filter((path) => path === "/dashboard")).toHaveLength(0);
    } else {
      await waitForMetrics(page);
      await expect(page.getByRole("group", { name: "Tổng số tài liệu", exact: true }).getByText(role === "admin" ? "128" : "27", { exact: true })).toBeVisible();
      await expect(page.getByRole("group", { name: "Tài liệu tải lên trong 7 ngày", exact: true }).getByText("15", { exact: true })).toBeVisible();
      await expect(main.getByText(role === "admin" ? "Phạm vi: toàn hệ thống" : "Phạm vi: tài liệu do bạn tải lên", { exact: true })).toBeVisible();
      const chart = page.getByRole("figure", { name: "Số tài liệu tải lên theo ngày" });
      await expect(chart.getByRole("listitem")).toHaveCount(7);
      await expect(chart.getByRole("listitem").nth(2)).toContainText("5");
      await expect(chart.getByRole("listitem").nth(2)).toHaveAttribute("title", "Ngày 23/10/2026: 5 tài liệu");
      await expect(page.getByRole("figure", { name: "Số tài liệu theo thư mục" })).toContainText("Chưa phân loại");
      await expect(page.getByText("21/10/2026 – 27/10/2026", { exact: true })).toBeVisible();
      await expect(main.getByRole("group", { name: "Tổng số người dùng", exact: true })).toHaveCount(role === "admin" ? 1 : 0);
      if (role === "admin") {
        await expect(main.getByRole("group", { name: "Tổng số người dùng", exact: true })).toContainText("42");
        const roles = page.getByRole("figure", { name: "Số người dùng theo vai trò" });
        await expect(roles.getByRole("listitem")).toHaveCount(3);
        await expect(roles).toContainText("Quản trị viên");
        await expect(roles).toContainText("Giáo viên");
        await expect(roles).toContainText("Học sinh");
      }
    }
    expect(state.unexpected).toEqual([]);
    await main.getByRole("link", { name: "Tìm kiếm tài liệu", exact: true }).focus();
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/search$/);
  });
}

test("loading skeleton preserves metric/chart geometry and leaves quick actions usable", async ({ page }) => {
  const state = await openDashboard(page, { hold: true });
  try {
    const loading = page.getByRole("status", { name: "Đang tải thống kê" });
    await expect(loading).toBeVisible();
    await expect(page.getByRole("region", { name: "Thống kê tổng quan" })).toHaveAttribute("aria-busy", "true");
    await expect(page.getByRole("group", { name: "Tổng số tài liệu", exact: true })).toHaveCount(0);
    const quick = page.getByRole("navigation", { name: "Truy cập nhanh" });
    const before = await quick.boundingBox();
    state.release();
    await waitForMetrics(page);
    await expect(loading).toHaveCount(0);
    const after = await quick.boundingBox();
    expect(Math.abs(before.y - after.y)).toBeLessThan(36);
    await expect(page.getByRole("region", { name: "Thống kê tổng quan" })).toHaveAttribute("aria-busy", "false");
  } finally { state.release(); }
});

for (const status of [500, 403]) {
  test("API error " + status + " is distinct from empty data and retry recovers", async ({ page }) => {
    const state = await openDashboard(page, { status });
    const main = page.getByRole("main");
    await expect(main.getByRole("alert")).toContainText("Không tải được thống kê");
    await expect(page.getByRole("group", { name: "Tổng số tài liệu", exact: true })).toHaveCount(0);
    await expect(page.getByText("Bạn chưa tải tài liệu nào lên", { exact: true })).toHaveCount(0);
    const before = state.requests.filter((path) => path === "/dashboard").length;
    state.status = 200;
    await main.getByRole("button", { name: "Thử lại", exact: true }).click();
    await waitForMetrics(page);
    expect(state.requests.filter((path) => path === "/dashboard").length).toBeGreaterThan(before);
    await expect(main.getByRole("alert")).toHaveCount(0);
  });
}

test("network rejection is handled and retry remains available", async ({ page }) => {
  await mockDashboard(page);
  await page.route("http://localhost:8000/dashboard", (route) => route.abort("failed"));
  await page.goto("/dashboard");
  await expect(page.getByRole("main").getByRole("alert")).toContainText("Không tải được thống kê");
  await expect(page.getByRole("button", { name: "Thử lại", exact: true })).toBeEnabled();
});

for (const role of ["teacher", "admin"]) {
  test(role + " empty dashboard shows real zeros and actionable empty states", async ({ page }) => {
    await openDashboard(page, { role, empty: true });
    await waitForMetrics(page);
    await expect(page.getByRole("group", { name: "Tổng số tài liệu", exact: true }).getByText("0", { exact: true })).toBeVisible();
    await expect(page.getByText("Chưa có tài liệu tải lên trong 7 ngày này.", { exact: true })).toBeVisible();
    await expect(page.getByText("Chưa có tài liệu để thống kê theo thư mục.", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Thử lại", exact: true })).toHaveCount(0);
    await page.getByRole("link", { name: "Tải tài liệu đầu tiên", exact: true }).click();
    await expect(page).toHaveURL(/\/documents\/upload$/);
  });
}

test("no recent uploads does not imply an empty library", async ({ page }) => {
  await openDashboard(page, { noRecent: true });
  await waitForMetrics(page);
  await expect(page.getByText("Chưa có tài liệu tải lên trong 7 ngày này.", { exact: true })).toBeVisible();
  await expect(page.getByText("Bạn chưa tải tài liệu nào lên", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("figure", { name: "Số tài liệu theo thư mục" })).toBeVisible();
});

test("optional admin fields can be omitted without fabricated user metrics", async ({ page }) => {
  await openDashboard(page, { role: "admin", optionalMissing: true });
  await waitForMetrics(page);
  await expect(page.getByRole("group", { name: "Tổng số người dùng", exact: true })).toHaveCount(0);
  await expect(page.getByRole("figure", { name: "Số người dùng theo vai trò" })).toHaveCount(0);
});

test("teacher UI does not expose admin fields even if a payload contains them", async ({ page }) => {
  const state = await mockDashboard(page);
  state.payload.summary.total_users = 999;
  state.payload.charts.users_by_role = [{ label: "admin", count: 999 }];
  await page.goto("/dashboard");
  await waitForMetrics(page);
  await expect(page.getByRole("group", { name: "Tổng số người dùng", exact: true })).toHaveCount(0);
  await expect(page.getByRole("figure", { name: "Số người dùng theo vai trò" })).toHaveCount(0);
});

for (const role of ["student", "teacher", "admin"]) {
  for (const width of [320, 390, 768, 1024, 1440]) {
    test(role + " responsive dashboard at " + width, async ({ page }) => {
      await openDashboard(page, { role, width, longData: true });
      if (role !== "student") await waitForMetrics(page);
      await assertNoOverflow(page);
      const quick = page.getByRole("navigation", { name: "Truy cập nhanh" });
      await quick.scrollIntoViewIfNeeded();
      await assertNoOverflow(page);
      for (const link of await quick.getByRole("link").all()) {
        await link.focus();
        await expect(link).toBeFocused();
        const bounds = await link.boundingBox();
        expect(bounds.x).toBeGreaterThanOrEqual(0);
        expect(bounds.x + bounds.width).toBeLessThanOrEqual(width);
      }
    });
  }
}

test("captures dashboard desktop and mobile with representative contract data", async ({ page }) => {
  await openDashboard(page, { role: "admin" });
  await waitForMetrics(page);
  await page.setViewportSize({ width: 1440, height: 1400 });
  await page.screenshot({ path: test.info().outputPath("dashboard-admin-desktop.png"), animations: "disabled" });
  await page.unrouteAll();
  await mockDashboard(page, { role: "teacher" });
  await page.setViewportSize({ width: 1440, height: 1100 });
  await page.reload();
  await waitForMetrics(page);
  await page.screenshot({ path: test.info().outputPath("dashboard-teacher-desktop.png"), animations: "disabled" });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: test.info().outputPath("dashboard-mobile.png"), animations: "disabled" });
  await page.getByRole("figure", { name: "Số tài liệu tải lên theo ngày" }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: test.info().outputPath("dashboard-mobile-analytics.png"), animations: "disabled" });
  await page.getByRole("navigation", { name: "Truy cập nhanh" }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: test.info().outputPath("dashboard-mobile-actions.png"), animations: "disabled" });
  await page.unrouteAll();
  await mockDashboard(page, { role: "student" });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.reload();
  await expect(page.getByRole("heading", { name: "Bắt đầu từ một tài liệu" })).toBeVisible();
  await page.screenshot({ path: test.info().outputPath("dashboard-student-desktop.png"), animations: "disabled" });
});
