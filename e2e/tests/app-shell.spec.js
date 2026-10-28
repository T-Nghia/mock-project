const { test, expect } = require("@playwright/test");

test.use({ channel: process.env.UI_BROWSER_CHANNEL || undefined, video: "off" });

async function mockApi(page, { role = "teacher", signedIn = true, longIdentity = false } = {}) {
  let authenticated = signedIn;
  const requests = [];
  const user = {
    id: "user-1",
    full_name: longIdentity ? "Nguyễn Thị Minh Anh — Không gian nghiên cứu học tập" : "Nguyễn Minh Anh",
    email: longIdentity ? "nguyen.thi.minh.anh.research.workspace@university.example.edu.vn" : "minhanh@slrms.edu.vn",
    role,
    is_active: true,
    created_at: "2026-01-12T08:00:00Z",
  };
  await page.route("http://localhost:8000/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    requests.push({ path, method: request.method() });
    const headers = {
      "access-control-allow-origin": new URL(process.env.APP_URL).origin,
      "access-control-allow-credentials": "true",
      "access-control-allow-headers": "authorization, content-type",
      "access-control-allow-methods": "GET, POST, PATCH, PUT, DELETE, OPTIONS",
    };
    const respond = (body, status = 200) => route.fulfill({ status, headers, contentType: "application/json", body: JSON.stringify(body) });
    if (request.method() === "OPTIONS") return route.fulfill({ status: 204, headers });
    if (path === "/auth/login") {
      authenticated = true;
      return respond({ access_token: "ui-test-token", token_type: "bearer" });
    }
    if (path === "/auth/refresh") return authenticated ? respond({ access_token: "ui-test-token", token_type: "bearer" }) : respond({ detail: "Unauthorized" }, 401);
    if (path === "/auth/logout") {
      authenticated = false;
      return route.fulfill({ status: 204, headers });
    }
    if (path === "/auth/me") return authenticated ? respond(user) : respond({ detail: "Unauthorized" }, 401);
    if (path === "/dashboard" && role === "student") return respond({ detail: "Dashboard is not available for students." }, 403);
    if (path === "/dashboard") return respond({
      role,
      summary: { total_documents: 128, ...(role === "admin" ? { total_users: 42 } : {}) },
      charts: {
        uploads_by_day: [
          { date: "2026-10-20", count: 4 }, { date: "2026-10-21", count: 8 },
          { date: "2026-10-22", count: 5 }, { date: "2026-10-23", count: 12 },
          { date: "2026-10-24", count: 0 }, { date: "2026-10-25", count: 2 }, { date: "2026-10-26", count: 1 },
        ],
        documents_by_folder: [{ label: "Học máy", count: 42 }, { label: "Xử lý ngôn ngữ", count: 35 }, { label: "Tài liệu tham khảo", count: 51 }],
        ...(role === "admin" ? { users_by_role: [{ label: "teacher", count: 12 }, { label: "student", count: 29 }, { label: "admin", count: 1 }] } : {}),
      },
    });
    if (path === "/search") return respond({ items: [], total: 0, page: 1, page_size: 10, total_pages: 0 });
    if (path === "/me/bookmarks") return respond({ items: [], total: 0, page: 1, page_size: 50 });
    if (path === "/folders") return role === "teacher" ? respond([]) : respond({ detail: "Khong co quyen truy cap" }, 403);
    if (path === "/folders/tree") return respond([{ id: "folder-1", name: "Học máy", subject: "AI", parent_folder_id: null, owner_id: user.id, created_at: user.created_at, children: [] }]);
    if (path === "/folders/folder-1/documents") return respond([]);
    if (path === "/documents/doc-1") return respond({
      id: "doc-1", title: "Nhập môn học máy", file_type: "txt", file_size: 1024, folder_id: null,
      uploaded_by: { id: user.id, full_name: user.full_name }, summary: "Các khái niệm nền tảng về học máy.",
      suggested_questions: ["Tóm tắt nội dung tài liệu"], processing_status: "done", tags: ["AI"], created_at: user.created_at,
    });
    if (path === "/documents/doc-1/bookmark") return respond({ document_id: "doc-1", bookmarked: false });
    if (path === "/documents/doc-1/rating") return respond({ document_id: "doc-1", average: null, count: 0, my_score: null });
    if (path === "/documents/doc-1/comments") return respond({ items: [], total: 0, page: 1, page_size: 50 });
    if (path === "/chat/documents/doc-1/sessions") return respond([{ id: "session-1", document_id: "doc-1", title: "Nội dung chính", created_at: user.created_at }]);
    if (path === "/chat/sessions/session-1") return respond({ id: "session-1", document_id: "doc-1", title: "Nội dung chính", created_at: user.created_at, messages: [] });
    if (path === "/chat/sessions/session-1/messages") return respond({ detail: "Vui lòng thử lại sau." }, 503);
    if (path === "/documents/doc-1/view") return route.fulfill({ status: 200, headers, contentType: "text/plain", body: "Tài liệu kiểm tra trình xem hiện có." });
    return respond({ detail: "Unexpected UI test request: " + path }, 404);
  });
  return requests;
}

async function openDashboard(page, options) {
  const requests = await mockApi(page, options);
  await page.goto("/dashboard");
  await expect(page.getByRole("heading", { name: /Chào mừng/ })).toBeVisible();
  return requests;
}

for (const [role, count] of [["student", 3], ["teacher", 5], ["admin", 6]]) {
  test("desktop navigation preserves " + role + " permissions", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await openDashboard(page, { role });
    const navigation = page.getByRole("navigation", { name: "Điều hướng chính" });
    await expect(navigation.getByRole("link")).toHaveCount(count);
    await expect(navigation.getByRole("link", { name: "Tổng quan" })).toHaveAttribute("aria-current", "page");
    await expect(navigation.getByRole("link", { name: "Người dùng" })).toHaveCount(role === "admin" ? 1 : 0);
    await expect(navigation.getByRole("link", { name: "Tải tài liệu lên" })).toHaveCount(role === "student" ? 0 : 1);
  });
}

test("sidebar collapse persists after refresh and retains named links", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const requests = await openDashboard(page);
  await page.getByRole("button", { name: "Thu gọn thanh điều hướng", exact: true }).click();
  const sidebar = page.getByRole("complementary", { name: "Thanh điều hướng" });
  await expect(sidebar).toHaveCSS("width", "64px");
  await expect(page.getByRole("link", { name: "Thư viện tài liệu", exact: true })).toBeVisible();
  await page.screenshot({ path: test.info().outputPath("sidebar-collapsed.png"), fullPage: true, animations: "disabled" });
  await page.reload();
  await expect(page.getByRole("heading", { name: /Chào mừng/ })).toBeVisible();
  await expect(sidebar).toHaveCSS("width", "64px");
  expect(requests.filter((request) => request.path === "/auth/refresh" && request.method === "POST").length).toBeGreaterThanOrEqual(2);
  await page.getByRole("button", { name: "Mở rộng thanh điều hướng" }).press("Enter");
  await expect(sidebar).toHaveCSS("width", "240px");
});

test("mobile drawer traps focus, closes on Escape and restores its trigger", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await openDashboard(page);
  const trigger = page.getByRole("button", { name: "Mở thanh điều hướng", exact: true });
  await trigger.click();
  const drawer = page.getByRole("dialog", { name: "Điều hướng SLRMS" });
  await expect(drawer).toBeVisible();
  await expect(trigger).toHaveAttribute("aria-expanded", "true");
  for (let index = 0; index < 10; index++) {
    await page.keyboard.press("Tab");
    expect(await drawer.evaluate((element) => element.contains(document.activeElement))).toBe(true);
  }
  await page.screenshot({ path: test.info().outputPath("mobile-drawer.png"), fullPage: true, animations: "disabled" });
  await page.keyboard.press("Escape");
  await expect(drawer).not.toBeVisible();
  await expect(trigger).toBeFocused();
  await expect(page.locator("body")).not.toHaveCSS("overflow", "hidden");
});

test("mobile navigation closes on selection, backdrop and desktop resize", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await openDashboard(page);
  const trigger = page.getByRole("button", { name: "Mở thanh điều hướng", exact: true });
  const drawer = page.getByRole("dialog", { name: "Điều hướng SLRMS" });
  await trigger.click();
  await drawer.getByRole("link", { name: "Thư viện tài liệu" }).click();
  await expect(page).toHaveURL(/\/search$/);
  await expect(drawer).not.toBeVisible();
  await trigger.click();
  await page.mouse.click(370, 400);
  await expect(drawer).not.toBeVisible();
  await trigger.click();
  await page.setViewportSize({ width: 1440, height: 900 });
  await expect(drawer).not.toBeVisible();
  await expect(page.locator("body")).not.toHaveCSS("overflow", "hidden");
  await page.getByRole("link", { name: "Tổng quan", exact: true }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
});

test("account menu supports arrows, Home, End and opens a labelled profile dialog", async ({ page }) => {
  await openDashboard(page);
  const trigger = page.getByRole("button", { name: "Mở menu tài khoản" });
  await trigger.focus();
  await page.keyboard.press("ArrowDown");
  const profile = page.getByRole("menuitem", { name: "Hồ sơ của tôi" });
  const logout = page.getByRole("menuitem", { name: "Đăng xuất" });
  await expect(profile).toBeFocused();
  await page.keyboard.press("ArrowUp");
  await expect(logout).toBeFocused();
  await page.keyboard.press("Home");
  await expect(profile).toBeFocused();
  await page.keyboard.press("End");
  await expect(logout).toBeFocused();
  await page.keyboard.press("Home");
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog", { name: "Hồ sơ của tôi" });
  await expect(dialog).toBeVisible();
  await expect(dialog).toHaveAttribute("aria-modal", "true");
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
  await expect(trigger).toBeFocused();
  await trigger.click();
  await profile.click();
  await page.mouse.click(5, 300);
  await expect(dialog).not.toBeVisible();
  await expect(trigger).toBeFocused();
});

test("account menu Tab and logout preserve navigation and the existing auth action", async ({ page }) => {
  const requests = await openDashboard(page);
  const trigger = page.getByRole("button", { name: "Mở menu tài khoản" });
  await trigger.click();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("menu")).not.toBeVisible();
  await trigger.click();
  await page.getByRole("menuitem", { name: "Đăng xuất" }).click();
  await expect(page).toHaveURL(/\/login$/);
  expect(requests.some((request) => request.path === "/auth/logout" && request.method === "POST")).toBe(true);
});

test("skip link moves keyboard focus to the main content", async ({ page }) => {
  await openDashboard(page);
  await page.keyboard.press("Tab");
  const skip = page.getByRole("link", { name: "Chuyển đến nội dung chính" });
  await expect(skip).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("main")).toBeFocused();
});

test("unauthenticated and student-only route guards are preserved", async ({ page }) => {
  await mockApi(page, { signedIn: false });
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/login$/);
  await page.unrouteAll();
  await mockApi(page, { role: "student" });
  for (const route of ["/folders", "/documents/upload", "/admin/users"]) {
    await page.goto(route);
    await expect(page).toHaveURL(/\/dashboard$/);
    await expect(page.getByRole("heading", { name: /Chào mừng/ })).toBeVisible();
  }
});

test("folder actions remain keyboard accessible", async ({ page }) => {
  await mockApi(page);
  await page.goto("/folders");
  const trigger = page.getByRole("button", { name: "Thao tác với thư mục Học máy" });
  await trigger.focus();
  await page.keyboard.press("ArrowDown");
  await expect(page.getByRole("menuitem", { name: "Thư mục con", exact: true })).toBeFocused();
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog", { name: "Chỉnh sửa thư mục" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByLabel("Tên thư mục")).toHaveValue("Học máy");
  await page.keyboard.press("Escape");
  await expect(trigger).toBeFocused();
});

test("workspace history Escape closes the popover and restores its trigger", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await mockApi(page);
  await page.goto("/documents/doc-1");
  const chat = page.getByRole("tabpanel", { name: "Trợ lý AI", exact: true });
  const trigger = chat.getByRole("button", { name: /Lịch sử/ });
  await trigger.click();
  const history = page.getByRole("dialog", { name: /Lịch sử/ });
  await expect(history).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(history).not.toBeVisible();
  await expect(trigger).toBeFocused();
  await expect(chat).toBeVisible();
});

test("notifications remain reachable in a modal and after it closes", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await mockApi(page);
  await page.goto("/documents/doc-1");
  const composer = page.getByLabel("Câu hỏi cho trợ lý AI");
  await expect(composer).toBeEnabled();
  await composer.fill("Tóm tắt giúp tôi");
  await composer.press("Enter");
  await expect(page.getByText("Không lấy được câu trả lời", { exact: true })).toBeVisible();
  await expect(composer).toHaveValue("Tóm tắt giúp tôi");
  await page.getByRole("button", { name: "Mở menu tài khoản" }).click();
  await page.getByRole("menuitem", { name: "Hồ sơ của tôi" }).click();
  const profile = page.getByRole("dialog", { name: "Hồ sơ của tôi" });
  await expect(profile.getByText("Không lấy được câu trả lời", { exact: true })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(profile).not.toBeVisible();
  await expect(page.getByText("Không lấy được câu trả lời", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Đóng thông báo" }).click();
  await expect(page.getByText("Không lấy được câu trả lời", { exact: true })).not.toBeVisible();
});
for (const width of [320, 768, 1024, 1440]) {
  test("shell and account overlay fit viewport " + width, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await openDashboard(page, { longIdentity: true });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({ path: test.info().outputPath("dashboard-" + width + ".png"), fullPage: true, animations: "disabled" });
    await page.getByRole("button", { name: "Mở menu tài khoản" }).click();
    const menu = page.getByRole("menu");
    const box = await menu.boundingBox();
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(width);
    await page.getByRole("menuitem", { name: "Hồ sơ của tôi" }).click();
    const dialog = page.getByRole("dialog", { name: "Hồ sơ của tôi" });
    await expect(dialog).toBeVisible();
    expect(await dialog.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);
    await page.screenshot({ path: test.info().outputPath("profile-" + width + ".png"), fullPage: true, animations: "disabled" });
  });
}
