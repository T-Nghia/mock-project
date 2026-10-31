const { test, expect, ids } = require("./remaining-pages-fixture");
test.use({ channel: process.env.UI_BROWSER_CHANNEL || undefined, video: "off" });
const root = (page) => page.getByRole("button", { name: "Nghiên cứu AI", exact: true });
async function menu(page, name, action) { await page.getByRole("button", { name: `Thao tác với thư mục ${name}`, exact: true }).click(); await page.getByRole("menuitem", { name: action, exact: true }).click(); }

for (const role of ["student", "admin"]) test(role + " has no folder actions or requests", async ({ page, mock }) => {
  const state = await mock({ role }); await page.goto("/folders");
  if (role === "student") await expect(page).toHaveURL(/\/dashboard$/);
  else await expect(page.getByRole("heading", { name: "Thư mục dành cho giáo viên" })).toBeVisible();
  await page.setViewportSize({ width: 1440, height: 900 });
  await expect(page.getByRole("navigation", { name: "Điều hướng chính" }).getByRole("link", { name: "Thư mục", exact: true })).toHaveCount(0);
  expect(state.calls.some((c) => c.path.startsWith("/folders"))).toBe(false);
});

test("teacher nested folders support keyboard, collapse, selection and dialog focus", async ({ page, mock }) => {
  await mock(); await page.goto("/folders");
  const toggle = page.getByRole("button", { name: "Thu gọn thư mục Nghiên cứu AI" });
  await toggle.focus(); await page.keyboard.press("Enter");
  await expect(page.getByRole("button", { name: "Học máy", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Mở rộng thư mục Nghiên cứu AI" }).click();
  await page.getByRole("button", { name: "Học máy", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Thư mục này chưa có tài liệu" })).toBeVisible();
  const trigger = page.getByRole("button", { name: "Thao tác với thư mục Nghiên cứu AI" });
  await trigger.focus(); await page.keyboard.press("ArrowDown"); await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog", { name: "Tạo thư mục mới" });
  await expect(dialog).toBeVisible(); await expect(dialog.getByText(/kế thừa/)).toBeVisible();
  await page.keyboard.press("Escape"); await expect(trigger).toBeFocused();
});

test("folder create and edit keep drafts on failure and preserve request contract", async ({ page, mock }) => {
  const state = await mock(); await page.goto("/folders");
  await page.getByRole("button", { name: "Tạo thư mục", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Tên thư mục").fill("  Đọc thêm  ");
  await dialog.getByLabel("Môn học (tuỳ chọn)").fill("Ngôn ngữ");
  state.failures["POST /folders"] = 409;
  await dialog.getByRole("button", { name: "Tạo thư mục", exact: true }).click();
  await expect(dialog.getByRole("alert")).toBeVisible(); await expect(dialog.getByLabel("Tên thư mục")).toHaveValue("  Đọc thêm  ");
  delete state.failures["POST /folders"];
  await dialog.getByRole("button", { name: "Tạo thư mục", exact: true }).click();
  await expect(dialog).toHaveCount(0); await expect(page.getByRole("button", { name: "Đọc thêm", exact: true })).toBeVisible();
  expect(state.calls.filter((c) => c.method === "POST" && c.path === "/folders").at(-1).body).toEqual({ name: "Đọc thêm", subject: "Ngôn ngữ", parent_folder_id: null });
  await root(page).click(); await menu(page, "Nghiên cứu AI", "Đổi tên / môn học");
  await dialog.getByLabel("Tên thư mục").fill("Nghiên cứu mới");
  await dialog.getByRole("button", { name: "Lưu thay đổi" }).click();
  await expect(page.getByRole("region", { name: "Tài liệu trong thư mục" }).getByRole("heading", { name: "Nghiên cứu mới" })).toBeVisible();
  const patch = state.calls.find((c) => c.method === "PATCH"); expect(patch.body).toEqual({ name: "Nghiên cứu mới", subject: "Trí tuệ nhân tạo" });
});

test("child creation sends parent ID and default subject; whitespace name is rejected", async ({ page, mock }) => {
  const state = await mock(); await page.goto("/folders"); await menu(page, "Nghiên cứu AI", "Thư mục con");
  const dialog = page.getByRole("dialog"); await dialog.getByLabel("Tên thư mục").fill("   ");
  await dialog.getByRole("button", { name: "Tạo thư mục", exact: true }).click(); await expect(dialog.getByRole("alert")).toContainText("nhập tên");
  expect(state.calls.filter((c) => c.method === "POST" && c.path === "/folders")).toHaveLength(0);
  await dialog.getByLabel("Tên thư mục").fill("Đề cương"); await dialog.getByRole("button", { name: "Tạo thư mục", exact: true }).click();
  await expect(page.getByRole("button", { name: "Đề cương", exact: true })).toBeVisible();
  expect(state.calls.find((c) => c.path === "/folders" && c.method === "POST").body).toEqual({ name: "Đề cương", subject: null, parent_folder_id: ids.root });
});

test("delete confirmation cancels, retains data on failure and removes selected descendant on success", async ({ page, mock }) => {
  const state = await mock(); await page.goto("/folders"); await page.getByRole("button", { name: "Học máy", exact: true }).click();
  await menu(page, "Nghiên cứu AI", "Xoá"); const dialog = page.getByRole("dialog", { name: "Xoá thư mục?" });
  await expect(dialog.getByRole("button", { name: "Huỷ" })).toBeFocused(); await page.keyboard.press("Escape");
  expect(state.calls.some((c) => c.method === "DELETE")).toBe(false);
  await menu(page, "Nghiên cứu AI", "Xoá"); state.failures[`DELETE /folders/${ids.root}`] = 500;
  await dialog.getByRole("button", { name: "Xoá thư mục", exact: true }).click(); await expect(dialog.getByRole("alert")).toBeVisible();
  expect(state.folders).toHaveLength(2); delete state.failures[`DELETE /folders/${ids.root}`];
  await dialog.getByRole("button", { name: "Xoá thư mục", exact: true }).click();
  await expect(dialog).toHaveCount(0); await expect(page.getByRole("heading", { name: "Chưa có thư mục nào" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Chọn một thư mục" })).toBeVisible(); expect(state.documents[0].folder_id).toBeNull();
});

test("document move restores selection after error and removes only after success", async ({ page, mock }) => {
  const state = await mock(); await page.goto("/folders"); await root(page).click();
  const select = page.getByLabel("Chuyển tài liệu tới", { exact: true }); await expect(select).toHaveValue(ids.root);
  state.failures[`PATCH /folders/documents/${ids.doc}`] = 500; await select.selectOption(ids.child);
  await expect(page.getByText("Chuyển thất bại", { exact: true })).toBeVisible(); await expect(select).toHaveValue(ids.root);
  await expect(page.getByRole("link", { name: state.documents[0].title, exact: true })).toBeVisible();
  delete state.failures[`PATCH /folders/documents/${ids.doc}`]; await select.selectOption(ids.child);
  await expect(page.getByRole("heading", { name: "Thư mục này chưa có tài liệu" })).toBeVisible();
  expect(state.calls.filter((c) => c.path.startsWith("/folders/documents/")).at(-1).body).toEqual({ folder_id: ids.child });
});

test("folder loading, error retry and empty states are distinct", async ({ page, mock }) => {
  const state = await mock({ empty: true }); const release = state.pause("GET /folders/tree");
  await page.goto("/folders"); await expect(page.getByRole("status", { name: "Đang tải thư mục" })).toBeVisible();
  state.failures["GET /folders/tree"] = 503; release(); await expect(page.getByRole("heading", { name: "Không tải được thư mục" })).toBeVisible();
  delete state.failures["GET /folders/tree"]; await page.getByRole("button", { name: "Thử lại", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Chưa có thư mục nào" })).toBeVisible();
});

test("folder document failures retry and old responses cannot overwrite selection", async ({ page, mock }) => {
  const state = await mock(); const release = state.pause(`GET /folders/${ids.root}/documents`);
  await page.goto("/folders"); await root(page).click(); await expect.poll(() => state.calls.some((c) => c.path === `/folders/${ids.root}/documents`)).toBe(true);
  await page.getByRole("button", { name: "Học máy", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Thư mục này chưa có tài liệu" })).toBeVisible(); release();
  await expect(page.getByRole("link", { name: state.documents[0].title, exact: true })).toHaveCount(0);
  state.failures[`GET /folders/${ids.root}/documents`] = 503; await root(page).click();
  await expect(page.getByRole("heading", { name: "Không tải được tài liệu" })).toBeVisible();
  delete state.failures[`GET /folders/${ids.root}/documents`]; await page.getByRole("button", { name: "Thử lại", exact: true }).click();
  await expect(page.getByRole("link", { name: state.documents[0].title, exact: true })).toBeVisible();
});
