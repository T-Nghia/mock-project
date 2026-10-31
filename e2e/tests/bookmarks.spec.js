const { test, expect, ids } = require("./remaining-pages-fixture");
test.use({ channel: process.env.UI_BROWSER_CHANNEL || undefined, video: "off" });

for (const role of ["student", "teacher", "admin"]) test(role + " bookmarks display API metadata and open workspace", async ({ page, mock }) => {
  const state = await mock({ role }); await page.goto("/bookmarks");
  await expect(page.getByRole("main")).toContainText("2 tài liệu đã lưu"); await expect(page.getByRole("main").getByText("Hoàn tất", { exact: true })).toHaveCount(2);
  const link = page.getByRole("link", { name: state.bookmarks[0].title, exact: true }); await link.focus(); await page.keyboard.press("Enter");
  await expect(page).toHaveURL(new RegExp(`/documents/${ids.doc}$`)); await expect(page.getByRole("heading", { name: state.documents[0].title, exact: true })).toBeVisible();
});

test("bookmarks paginate with API and recover when last item on page is removed", async ({ page, mock }) => {
  const state = await mock({ bookmarkCount: 21 }); await page.goto("/bookmarks");
  await expect(page.getByRole("main").getByRole("listitem")).toHaveCount(20);
  await page.getByRole("button", { name: "Tiếp theo", exact: true }).click();
  await expect(page.getByText("Trang 2/2", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: /^Bỏ lưu/ }).click(); await expect(page.getByText("Trang 1/1", { exact: true })).toBeVisible();
  expect(state.calls.filter((c) => c.path === "/me/bookmarks").some((c) => c.query.page === "2" && c.query.page_size === "20")).toBe(true);
});

test("failed bookmark removal retains item and explicit retry succeeds", async ({ page, mock }) => {
  const state = await mock(); await page.goto("/bookmarks"); state.failures[`DELETE /documents/${ids.doc}/bookmark`] = 503;
  const remove = page.getByRole("button", { name: `Bỏ lưu ${state.bookmarks[0].title}`, exact: true }); await remove.click();
  await expect(page.getByText("Không thể bỏ lưu", { exact: true })).toBeVisible(); await expect(remove).toBeEnabled();
  delete state.failures[`DELETE /documents/${ids.doc}/bookmark`]; const release = state.pause(`DELETE /documents/${ids.doc}/bookmark`);
  await remove.evaluate((el) => { el.click(); el.click(); }); await expect(remove).toBeDisabled(); release();
  await expect(remove).toHaveCount(0); await expect(page.getByRole("main")).toContainText("1 tài liệu đã lưu");
  expect(state.calls.filter((c) => c.method === "DELETE")).toHaveLength(2);
});

test("bookmarks loading error retry and empty state", async ({ page, mock }) => {
  const state = await mock({ empty: true }); const release = state.pause("GET /me/bookmarks"); await page.goto("/bookmarks");
  await expect(page.getByRole("status", { name: "Đang tải tài liệu đã lưu" })).toBeVisible(); state.failures["GET /me/bookmarks"] = 500; release();
  await expect(page.getByRole("heading", { name: "Không tải được tài liệu đã lưu" })).toBeVisible();
  delete state.failures["GET /me/bookmarks"]; await page.getByRole("button", { name: "Thử lại", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Bạn chưa lưu tài liệu nào" })).toBeVisible();
});
