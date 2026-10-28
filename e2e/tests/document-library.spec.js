const { test, expect } = require("@playwright/test");
const { mockLibraryUpload, assertFits, folderId, docId } = require("./library-upload-fixture");
test.use({ channel: process.env.UI_BROWSER_CHANNEL || undefined, video: "off" });
let errors;
test.beforeEach(({ page }) => { errors = []; page.on("pageerror", (error) => errors.push(error.message)); });
test.afterEach(() => expect(errors).toEqual([]));
const results = (page) => page.getByRole("region", { name: "Kết quả tài liệu" });
async function ready(page) { await expect(results(page)).toHaveAttribute("aria-busy", "false"); }

for (const role of ["student", "teacher", "admin"]) {
  test(role + " library uses real metadata, supported filters and role actions", async ({ page }) => {
    const state = await mockLibraryUpload(page, { role });
    await page.goto("/search"); await ready(page);
    await expect(page.getByRole("main").getByRole("link", { name: "Tải tài liệu lên", exact: true })).toHaveCount(role === "student" ? 0 : 1);
    await expect(page.getByLabel("Thư mục của bạn", { exact: true })).toHaveCount(role === "teacher" ? 1 : 0);
    expect(state.requests.filter((request) => request.path === "/folders")).toHaveLength(role === "teacher" ? 1 : 0);
    await expect(results(page).getByRole("link")).toHaveCount(10);
    await expect(results(page)).toContainText("12 tài liệu trong thư viện");
    await expect(results(page)).toContainText("txt");
    await expect(results(page)).not.toContainText("Đang xử lý");
    const before = state.searches.length;
    await page.getByRole("textbox", { name: "Tìm kiếm tài liệu", exact: true }).fill("RAG");
    expect(state.searches).toHaveLength(before);
    await page.getByRole("textbox", { name: "Tìm kiếm tài liệu", exact: true }).press("Enter"); await ready(page);
    await expect(page).toHaveURL(/keyword=RAG/);
    await expect(results(page)).toContainText("12 tài liệu phù hợp");
    expect(state.searches.at(-1).keyword).toBe("RAG");
    expect(state.unexpected).toEqual([]);
  });
}

test("pagination and filters persist across Back, Forward and reload", async ({ page }) => {
  const state = await mockLibraryUpload(page);
  await page.goto("/search"); await ready(page);
  await page.getByRole("button", { name: "Tiếp theo", exact: true }).click();
  await expect(page).toHaveURL(/page=2/); await ready(page);
  await expect(results(page)).toContainText("Trang 2/2");
  await expect(results(page).getByRole("link")).toHaveCount(2);
  await expect(page.getByRole("button", { name: "Tiếp theo", exact: true })).toBeDisabled();
  await page.getByLabel("Môn học", { exact: true }).fill("Trí tuệ");
  await page.getByLabel("Thẻ", { exact: true }).fill("không có, RAG");
  await page.getByLabel("Thư mục của bạn").selectOption(folderId);
  await page.getByRole("search").getByRole("button", { name: "Tìm kiếm", exact: true }).click();
  await expect(page).not.toHaveURL(/page=2/); await ready(page);
  await expect(results(page)).toContainText("6 tài liệu phù hợp");
  expect(state.searches.at(-1)).toMatchObject({ subject: "Trí tuệ", tags: ["không có", "RAG"], folder_id: folderId, page: "1", page_size: "10" });
  await page.reload(); await ready(page);
  await expect(page.getByLabel("Môn học", { exact: true })).toHaveValue("Trí tuệ");
  await expect(page.getByLabel("Thư mục của bạn")).toHaveValue(folderId);
  await page.goBack(); await ready(page);
  await expect(results(page)).toContainText("Trang 2/2");
  await expect(page.getByLabel("Môn học", { exact: true })).toHaveValue("");
  await page.goForward(); await ready(page);
  await expect(results(page)).toContainText("6 tài liệu phù hợp");
});

test("empty library differs from no matches; clear keyword and filters recover", async ({ page }) => {
  const state = await mockLibraryUpload(page, { empty: true });
  await page.goto("/search"); await ready(page);
  await expect(page.getByRole("heading", { name: "Thư viện chưa có tài liệu" })).toBeVisible();
  await page.getByRole("textbox", { name: "Tìm kiếm tài liệu", exact: true }).fill("không tồn tại");
  await page.getByRole("textbox", { name: "Tìm kiếm tài liệu", exact: true }).press("Enter"); await ready(page);
  await expect(page.getByRole("heading", { name: "Không tìm thấy tài liệu phù hợp" })).toBeVisible();
  await page.getByRole("button", { name: "Xóa từ khóa", exact: true }).click(); await ready(page);
  await expect(page.getByRole("textbox", { name: "Tìm kiếm tài liệu", exact: true })).toHaveValue("");
  await expect(page.getByRole("heading", { name: "Thư viện chưa có tài liệu" })).toBeVisible();
  expect(state.searches.at(-1).keyword).toBeUndefined();
});

test("out-of-range backend page is not misreported as an empty library", async ({ page }) => {
  await mockLibraryUpload(page);
  await page.goto("/search?page=99"); await ready(page);
  await expect(page.getByRole("heading", { name: "Trang này không còn kết quả" })).toBeVisible();
  await expect(page.getByText("0 tài liệu trong thư viện", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Về trang đầu" }).click(); await ready(page);
  await expect(results(page)).toContainText("12 tài liệu trong thư viện");
});

test("loading, API error and retry keep the applied search", async ({ page }) => {
  const state = await mockLibraryUpload(page);
  state.holdSearch = true;
  try {
    await page.goto("/search?keyword=RAG");
    await expect(page.getByRole("status", { name: "Đang tải tài liệu" })).toBeVisible();
    state.searchStatus = 503; state.releaseSearch();
    await expect(results(page).getByRole("alert")).toContainText("Không tải được thư viện");
    await expect(page.getByRole("textbox", { name: "Tìm kiếm tài liệu", exact: true })).toHaveValue("RAG");
    state.searchStatus = 200;
    await page.getByRole("button", { name: "Thử lại", exact: true }).click(); await ready(page);
    await expect(results(page)).toContainText("12 tài liệu phù hợp");
    expect(state.searches.at(-1).keyword).toBe("RAG");
  } finally { state.releaseSearch(); }
});

test("late response cannot replace a newer search; duplicate submit is ignored", async ({ page }) => {
  const state = await mockLibraryUpload(page);
  await page.goto("/search"); await ready(page);
  const input = page.getByRole("textbox", { name: "Tìm kiếm tài liệu", exact: true });
  await input.fill("slow"); await input.press("Enter");
  await expect.poll(() => state.slowSeen).toBe(true);
  await input.fill("no-match-new");
  await page.getByRole("search").getByRole("button", { name: "Tìm kiếm", exact: true }).evaluate((button) => { button.click(); button.click(); });
  await expect(page).toHaveURL(/keyword=no-match-new/);
  await expect(page.getByRole("heading", { name: "Không tìm thấy tài liệu phù hợp" })).toBeVisible();
  await expect.poll(() => state.slowCompleted).toBe(true);
  await expect(page.getByRole("heading", { name: "Không tìm thấy tài liệu phù hợp" })).toBeVisible();
  expect(state.searches.filter((query) => query.keyword === "no-match-new")).toHaveLength(1);
});

test("folder list failure is separate from search and retry works", async ({ page }) => {
  const state = await mockLibraryUpload(page); state.folderStatus = 503;
  await page.goto("/search"); await ready(page);
  await expect(page.getByLabel("Thư mục của bạn")).toBeDisabled();
  await expect(results(page)).toContainText("12 tài liệu trong thư viện");
  state.folderStatus = 200;
  await page.getByRole("button", { name: "Thử lại thư mục" }).click();
  await expect(page.getByLabel("Thư mục của bạn")).toBeEnabled();
  await page.getByLabel("Thư mục của bạn").selectOption(folderId);
});

test("document opens the existing workspace with keyboard navigation", async ({ page }) => {
  const state = await mockLibraryUpload(page, { role: "student" });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/search"); await ready(page);
  const link = results(page).getByRole("link").first();
  await link.focus(); await page.keyboard.press("Enter");
  await expect(page).toHaveURL(new RegExp(`/documents/${docId}$`));
  await expect(page.getByRole("heading", { name: state.documents[0].title, exact: true })).toBeVisible();
  await expect(page.getByRole("tabpanel", { name: "Tài liệu", exact: true })).toBeVisible();
  expect(state.unexpected).toEqual([]);
});

for (const width of [320, 390, 768, 1024, 1440]) {
  test("library responsive and keyboard with long metadata at " + width, async ({ page }) => {
    await mockLibraryUpload(page, { longData: true });
    await page.setViewportSize({ width, height: 1000 });
    await page.goto("/search"); await ready(page); await assertFits(page);
    await results(page).getByRole("link").first().focus();
    await expect(results(page).getByRole("link").first()).toBeFocused();
    await page.getByRole("navigation", { name: "Phân trang tài liệu" }).scrollIntoViewIfNeeded();
    await assertFits(page);
  });
}

test("captures library desktop and mobile", async ({ page }) => {
  await mockLibraryUpload(page);
  await page.setViewportSize({ width: 1440, height: 1100 });
  await page.goto("/search"); await ready(page);
  await page.screenshot({ path: test.info().outputPath("library-desktop.png"), animations: "disabled" });
  await page.setViewportSize({ width: 390, height: 1000 });
  await page.screenshot({ path: test.info().outputPath("library-mobile.png"), animations: "disabled" });
  await results(page).getByRole("link").first().scrollIntoViewIfNeeded();
  await page.screenshot({ path: test.info().outputPath("library-mobile-results.png"), animations: "disabled" });
});
