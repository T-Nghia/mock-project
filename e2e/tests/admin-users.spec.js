const { test, expect, ids } = require("./remaining-pages-fixture");
test.use({ channel: process.env.UI_BROWSER_CHANNEL || undefined, video: "off" });
for (const role of ["student", "teacher"]) test(role + " cannot access user administration", async ({ page, mock }) => {
  const state = await mock({ role }); await page.goto("/admin/users"); await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByRole("heading", { name: /Chào mừng/ })).toBeVisible(); expect(state.calls.some((c) => c.path.startsWith("/auth/admin/"))).toBe(false);
});

test("admin sees actual roles status and cannot modify own account", async ({ page, mock }) => {
  await mock({ role: "admin" }); await page.goto("/admin/users"); const list = page.getByRole("list", { name: "Danh sách người dùng" });
  await expect(list.getByRole("listitem")).toHaveCount(2); await expect(list).toContainText("Quản trị viên"); await expect(list).toContainText("Học sinh");
  await expect(page.getByRole("combobox", { name: "Vai trò của minhanh@example.com" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Khoá minhanh@example.com", exact: true })).toBeDisabled();
});

test("role change requires confirmation; cancel and API error retain old role", async ({ page, mock }) => {
  const state = await mock({ role: "admin" }); await page.goto("/admin/users");
  const select = page.getByRole("combobox", { name: "Vai trò của baongoc@example.com" });
  await select.focus(); await select.selectOption("teacher"); let dialog = page.getByRole("dialog", { name: "Xác nhận đổi vai trò" });
  await expect(dialog).toContainText("Giáo viên"); expect(state.calls.some((c) => c.method === "PATCH")).toBe(false);
  await page.keyboard.press("Escape"); await expect(select).toHaveValue("student"); await expect(select).toBeFocused();
  await select.selectOption("teacher"); state.failures[`PATCH /auth/admin/users/${ids.other}/role`] = 400;
  await dialog.getByRole("button", { name: "Xác nhận", exact: true }).click(); await expect(dialog.getByRole("alert")).toBeVisible();
  expect(state.users[1].role).toBe("student"); delete state.failures[`PATCH /auth/admin/users/${ids.other}/role`];
  await dialog.getByRole("button", { name: "Xác nhận", exact: true }).click(); await expect(dialog).toHaveCount(0); await expect(select).toHaveValue("teacher");
  expect(state.calls.filter((c) => c.method === "PATCH").at(-1).body).toEqual({ role: "teacher" });
});

test("status change confirms, locks duplicate submits and can unlock", async ({ page, mock }) => {
  const state = await mock({ role: "admin" }); await page.goto("/admin/users");
  await page.getByRole("button", { name: "Khoá baongoc@example.com", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Xác nhận trạng thái tài khoản" }); const release = state.pause(`PATCH /auth/admin/users/${ids.other}/status`);
  await dialog.getByRole("button", { name: "Xác nhận", exact: true }).evaluate((el) => { el.click(); el.click(); });
  await expect(dialog.getByRole("button", { name: "Xác nhận", exact: true })).toBeDisabled(); await page.keyboard.press("Escape"); await expect(dialog).toBeVisible(); release();
  await expect(dialog).toHaveCount(0); await page.getByRole("button", { name: "Mở khoá baongoc@example.com", exact: true }).click();
  await dialog.getByRole("button", { name: "Xác nhận", exact: true }).click(); await expect(dialog).toHaveCount(0);
  expect(state.calls.filter((c) => c.path.endsWith("/status")).map((c) => c.body)).toEqual([{ is_active: false }, { is_active: true }]);
});

test("create teacher validates, retains fields on failure and refreshes list", async ({ page, mock }) => {
  const state = await mock({ role: "admin" }); await page.goto("/admin/users"); await page.getByRole("button", { name: "Thêm giáo viên" }).click();
  const dialog = page.getByRole("dialog", { name: "Thêm tài khoản giáo viên" });
  await dialog.getByRole("button", { name: "Tạo tài khoản", exact: true }).click(); expect(state.calls.some((c) => c.path === "/auth/admin/teachers")).toBe(false);
  await dialog.getByLabel("Họ và tên", { exact: true }).fill("Giáo viên mới"); await dialog.getByLabel("Email", { exact: true }).fill("teacher@example.com");
  await dialog.getByLabel("Mật khẩu tạm thời", { exact: true }).fill("Temporary123!"); state.failures["POST /auth/admin/teachers"] = 409;
  await dialog.getByRole("button", { name: "Tạo tài khoản", exact: true }).click(); await expect(dialog.getByRole("alert")).toBeVisible();
  await expect(dialog.getByLabel("Email", { exact: true })).toHaveValue("teacher@example.com"); delete state.failures["POST /auth/admin/teachers"];
  await dialog.getByRole("button", { name: "Tạo tài khoản", exact: true }).click(); await expect(dialog).toHaveCount(0);
  await expect(page.getByRole("list", { name: "Danh sách người dùng" })).toContainText("Giáo viên mới");
  expect(state.calls.filter((c) => c.path === "/auth/admin/teachers").at(-1).body).toEqual({ full_name: "Giáo viên mới", email: "teacher@example.com", password: "Temporary123!" });
});

test("users loading error retry and empty states", async ({ page, mock }) => {
  const state = await mock({ role: "admin", empty: true }); const release = state.pause("GET /auth/admin/users"); await page.goto("/admin/users");
  await expect(page.getByRole("status", { name: "Đang tải người dùng" })).toBeVisible(); state.failures["GET /auth/admin/users"] = 503; release();
  await expect(page.getByRole("heading", { name: "Không tải được danh sách người dùng" })).toBeVisible();
  delete state.failures["GET /auth/admin/users"]; await page.getByRole("button", { name: "Thử lại", exact: true }).click(); await expect(page.getByRole("heading", { name: "Chưa có người dùng" })).toBeVisible();
});
