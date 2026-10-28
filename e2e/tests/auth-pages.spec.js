const { test, expect } = require("./remaining-pages-fixture");
test.use({ channel: process.env.UI_BROWSER_CHANNEL || undefined, video: "off" });
const password = "Learning123!";
async function loginFields(page) { await page.getByLabel("Email", { exact: true }).fill("student@example.com"); await page.getByLabel("Mật khẩu", { exact: true }).fill(password); }

test("login validation, password toggle, loading, duplicate prevention and dashboard redirect", async ({ page, mock }) => {
  const state = await mock({ public: true, role: "student" }); await page.goto("/login");
  await page.getByRole("button", { name: "Đăng nhập", exact: true }).click(); expect(state.calls.some((c) => c.path === "/auth/login")).toBe(false);
  await loginFields(page); const toggle = page.getByRole("button", { name: "Hiện mật khẩu", exact: true }); await toggle.focus(); await page.keyboard.press("Enter");
  await expect(page.getByLabel("Mật khẩu", { exact: true })).toHaveAttribute("type", "text");
  await page.getByRole("button", { name: "Ẩn mật khẩu", exact: true }).click(); const release = state.pause("POST /auth/login");
  await page.getByRole("button", { name: "Đăng nhập", exact: true }).evaluate((el) => { el.click(); el.click(); });
  await expect(page.getByRole("button", { name: "Đang đăng nhập…", exact: true })).toBeDisabled(); await expect(page.getByLabel("Email", { exact: true })).toBeDisabled();
  release(); await expect(page).toHaveURL(/\/dashboard$/); await expect(page.getByRole("heading", { name: /Chào mừng/ })).toBeVisible();
  const calls = state.calls.filter((c) => c.path === "/auth/login"); expect(calls).toHaveLength(1); expect(calls[0].body).toEqual({ email: "student@example.com", password });
  await page.reload(); await expect(page.getByRole("heading", { name: /Chào mừng/ })).toBeVisible();
});

for (const status of [401, 429, 500]) test("login handles " + status + " without leaking server diagnostics", async ({ page, mock }) => {
  const state = await mock({ public: true }); state.failures["POST /auth/login"] = status; await page.goto("/login"); await loginFields(page);
  await page.getByRole("button", { name: "Đăng nhập", exact: true }).click(); await expect(page.getByRole("main").getByRole("alert")).toContainText(status < 500 ? "Yêu cầu chưa được chấp nhận" : "Đăng nhập thất bại");
  await expect(page.getByRole("main").getByRole("alert")).not.toContainText("Internal diagnostic"); await expect(page.getByLabel("Email", { exact: true })).toHaveValue("student@example.com");
  await expect(page).toHaveURL(/\/login$/);
});

test("registration matches passwords, preserves draft on error and returns to login", async ({ page, mock }) => {
  const state = await mock({ public: true }); await page.goto("/register");
  await page.getByLabel("Họ và tên", { exact: true }).fill("Học sinh mới"); await page.getByLabel("Email", { exact: true }).fill("student@example.com");
  await page.getByLabel("Mật khẩu", { exact: true }).fill(password); await page.getByLabel("Xác nhận mật khẩu", { exact: true }).fill("Different123!");
  await page.getByRole("button", { name: "Đăng ký", exact: true }).click(); await expect(page.getByRole("main").getByRole("alert")).toContainText("không khớp");
  await expect(page.getByLabel("Xác nhận mật khẩu", { exact: true })).toBeFocused(); expect(state.calls.some((c) => c.path === "/auth/register")).toBe(false);
  await page.getByLabel("Xác nhận mật khẩu", { exact: true }).fill(password); state.failures["POST /auth/register"] = 409;
  await page.getByRole("button", { name: "Đăng ký", exact: true }).click(); await expect(page.getByRole("main").getByRole("alert")).toContainText("Yêu cầu chưa được chấp nhận");
  await expect(page.getByLabel("Họ và tên", { exact: true })).toHaveValue("Học sinh mới"); delete state.failures["POST /auth/register"];
  await page.getByRole("button", { name: "Đăng ký", exact: true }).click(); await expect(page).toHaveURL(/\/login$/);
  expect(state.calls.filter((c) => c.path === "/auth/register").at(-1).body).toEqual({ full_name: "Học sinh mới", email: "student@example.com", password, confirm_password: password });
  expect(state.authenticated).toBe(false);
});

test("forgot password uses generic success and exact contract; failure is retryable", async ({ page, mock }) => {
  const state = await mock({ public: true }); await page.goto("/forgot-password"); await page.getByLabel("Email", { exact: true }).fill("unknown@example.com");
  state.failures["POST /auth/forgot-password"] = 429; await page.getByRole("button", { name: "Gửi liên kết đặt lại mật khẩu" }).click(); await expect(page.getByRole("main").getByRole("alert")).toBeVisible();
  delete state.failures["POST /auth/forgot-password"]; const release = state.pause("POST /auth/forgot-password");
  await page.getByRole("button", { name: "Gửi liên kết đặt lại mật khẩu" }).click(); await expect(page.getByRole("button", { name: "Đang gửi yêu cầu…" })).toBeDisabled(); release();
  await expect(page.getByRole("status")).toContainText("Nếu email unknown@example.com tồn tại");
  expect(state.calls.filter((c) => c.path === "/auth/forgot-password").at(-1).body).toEqual({ email: "unknown@example.com" });
});

test("missing reset token blocks submit and provides recovery link", async ({ page, mock }) => {
  const state = await mock({ public: true }); await page.goto("/reset-password"); await expect(page.getByRole("main").getByRole("alert")).toContainText("Không tìm thấy mã");
  await expect(page.getByRole("button", { name: "Đặt lại mật khẩu", exact: true })).toHaveCount(0); await expect(page.getByRole("link", { name: "Yêu cầu liên kết mới" })).toHaveAttribute("href", "/forgot-password");
  expect(state.calls.some((c) => c.path === "/auth/reset-password")).toBe(false);
});

test("reset token error, confirmation validation, loading and successful return to login", async ({ page, mock }) => {
  const state = await mock({ public: true }); await page.goto("/reset-password?token=test-reset-token");
  await page.getByLabel("Mật khẩu mới", { exact: true }).fill(password); await page.getByLabel("Nhập lại mật khẩu mới", { exact: true }).fill("Different123!");
  await page.getByRole("button", { name: "Đặt lại mật khẩu", exact: true }).click(); await expect(page.getByRole("main").getByRole("alert")).toContainText("không khớp");
  await page.getByLabel("Nhập lại mật khẩu mới", { exact: true }).fill(password); state.failures["POST /auth/reset-password"] = 400;
  await page.getByRole("button", { name: "Đặt lại mật khẩu", exact: true }).click(); await expect(page.getByRole("main").getByRole("alert")).toContainText("Yêu cầu chưa được chấp nhận");
  delete state.failures["POST /auth/reset-password"]; const release = state.pause("POST /auth/reset-password"); await page.getByRole("button", { name: "Đặt lại mật khẩu", exact: true }).click();
  await expect(page.getByRole("button", { name: "Đang cập nhật…" })).toBeDisabled(); release(); await expect(page.getByRole("status")).toContainText("thành công");
  expect(state.calls.filter((c) => c.path === "/auth/reset-password").at(-1).body).toEqual({ token: "test-reset-token", new_password: password, confirm_new_password: password });
  await page.getByRole("button", { name: "Đăng nhập ngay" }).click(); await expect(page).toHaveURL(/\/login$/);
});

test("public root and protected routes keep existing unauthenticated redirects", async ({ page, mock }) => {
  await mock({ public: true });
  for (const path of ["/", "/dashboard", "/folders", "/bookmarks", "/admin/users"]) { await page.goto(path); await expect(page).toHaveURL(/\/login$/); }
});
