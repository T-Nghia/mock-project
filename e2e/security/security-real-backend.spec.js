const { test, expect } = require("@playwright/test");
const fs = require("node:fs/promises");

test.beforeAll(() => {
  // Fail, rather than skip, if somebody selects this suite without its sandbox.
  expect(process.env.SECURITY_ISOLATED_TEST).toBe("1");
  expect(process.env.APP_URL).toBe("http://localhost:3000");
  expect(process.env.API_URL).toBe("http://localhost:8000");
  expect(process.env.SECURITY_TEST_PASSWORD).toBeTruthy();
});

async function login(page) {
  await page.goto("/login");
  // next dev can serve the prerendered form before client handlers hydrate.
  // This isolated page has no long polling; wait for bootstrap to settle.
  await page.waitForLoadState("networkidle");
  await page.getByLabel("Email", { exact: true }).fill("security.teacher@example.com");
  await page.getByLabel("Mật khẩu", { exact: true }).fill(process.env.SECURITY_TEST_PASSWORD);
  await page.getByRole("button", { name: "Đăng nhập", exact: true }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
}

test("real auth cookie restores dashboard and folders across reload; logout revokes access", async ({ page }) => {
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await login(page);
  await expect(page.getByRole("heading", { name: /Chào/ })).toBeVisible();
  await page.goto("/folders");
  await page.getByRole("button", { name: "Tạo thư mục", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Tên thư mục").fill("Security regression folder");
  await dialog.getByRole("button", { name: "Tạo thư mục", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Security regression folder", exact: true })).toBeVisible();
  const refreshRequests = [];
  const recordRefresh = (r) => { if (r.url().endsWith("/auth/refresh")) refreshRequests.push(r.url()); };
  page.on("request", recordRefresh);
  const refreshed = page.waitForResponse((r) => r.url().endsWith("/auth/refresh") && r.status() === 200);
  await page.reload();
  await refreshed;
  await expect(page.getByRole("button", { name: "Security regression folder", exact: true })).toBeVisible();
  page.off("request", recordRefresh);
  expect(refreshRequests).toHaveLength(1);
  await page.getByRole("button", { name: "Mở menu tài khoản" }).click();
  await page.getByRole("menuitem", { name: "Đăng xuất" }).click();
  await expect(page).toHaveURL(/\/login$/);
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/login$/);
  expect(errors).toEqual([]);
});

test("real upload, S3 preview/download, bookmark, rating and grounded chat survive Next16", async ({ page }) => {
  const errors = [];
  const optimizerRequests = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("request", (r) => { if (new URL(r.url()).pathname === "/_next/image") optimizerRequests.push(r.url()); });
  await login(page);
  await page.goto("/documents/upload");
  const text = "Security regression document stored in isolated MinIO.\n";
  await page.getByLabel("Tệp tài liệu", { exact: true }).setInputFiles({
    name: "security-regression.txt", mimeType: "text/plain", buffer: Buffer.from(text),
  });
  await page.getByLabel("Tiêu đề", { exact: false }).fill("Next16 real storage regression");
  await page.getByRole("button", { name: "Tải lên", exact: true }).click();
  await page.getByRole("link", { name: "Mở tài liệu", exact: true }).click();
  await expect(page).toHaveURL(/\/documents\/[0-9a-f-]{36}$/);
  // Background processing is real; the test-only AI provider is deterministic.
  await expect(async () => {
    await page.reload();
    await page.getByRole("tab", { name: "Thông tin & thảo luận", exact: true }).click();
    await expect(page.getByText("Hoàn tất", { exact: true })).toBeVisible();
  }).toPass({ timeout: 10000 });
  await expect(page.getByText("Security regression summary.", { exact: true })).toBeVisible();
  await page.getByRole("tab", { name: "Đọc tài liệu", exact: true }).click();
  await expect(page.getByText(text.trim(), { exact: true })).toBeVisible();
  await page.getByRole("tab", { name: "Thông tin & thảo luận", exact: true }).click();
  await page.getByRole("button", { name: "Lưu tài liệu", exact: true }).click();
  await expect(page.getByRole("button", { name: "Đã lưu", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Đánh giá 5 sao", exact: true }).click();
  await expect(page.getByRole("button", { name: "Đánh giá 5 sao", exact: true })).toHaveAttribute("aria-pressed", "true");
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Tải xuống tài liệu", exact: true }).click();
  const downloaded = await download;
  // The develop API's CORS contract does not expose Content-Disposition;
  // preserve the existing client fallback instead of changing that contract.
  expect(downloaded.suggestedFilename()).toBe("document.txt");
  expect(await fs.readFile(await downloaded.path(), "utf8")).toBe(text);
  await page.getByRole("textbox", { name: "Câu hỏi cho trợ lý AI" }).fill("What is this document about?");
  await page.getByRole("button", { name: "Gửi câu hỏi", exact: true }).click();
  await expect(page.getByText("Isolated security regression answer.", { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByText("Isolated security regression answer.", { exact: true })).toBeVisible();
  expect(optimizerRequests).toEqual([]);
  expect(errors).toEqual([]);
});
