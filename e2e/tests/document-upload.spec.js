const { test, expect } = require("@playwright/test");
const { mockLibraryUpload, assertFits, folderId, docId, validFile } = require("./library-upload-fixture");
test.use({ channel: process.env.UI_BROWSER_CHANNEL || undefined, video: "off" });
let errors;
test.beforeEach(({ page }) => { errors = []; page.on("pageerror", (error) => errors.push(error.message)); });
test.afterEach(() => expect(errors).toEqual([]));
async function openUpload(page, options = {}) {
  const state = await mockLibraryUpload(page, options);
  await page.goto("/documents/upload");
  if (options.role !== "student") await expect(page.getByRole("main").getByRole("heading", { name: "Tải tài liệu lên", exact: true })).toBeVisible();
  return state;
}
async function selectFile(page, file = validFile) {
  await page.getByLabel("Tệp tài liệu", { exact: true }).setInputFiles(file);
  await expect(page.getByText(file.name, { exact: true })).toBeVisible();
  await expect(page.getByText("Đang kiểm tra tệp…", { exact: true })).toHaveCount(0);
}

test("student cannot access upload or trigger its endpoints", async ({ page }) => {
  const state = await openUpload(page, { role: "student" });
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByRole("heading", { name: /Chào mừng/ })).toBeVisible();
  expect(state.requests.some((request) => request.path === "/folders" || request.path === "/documents/upload")).toBe(false);
  await expect(page.getByLabel("Tệp tài liệu", { exact: true })).toHaveCount(0);
});

for (const role of ["teacher", "admin"]) {
  test(role + " upload preserves multipart contract and distinguishes processing", async ({ page }) => {
    const state = await openUpload(page, { role });
    await selectFile(page);
    await page.getByLabel("Tiêu đề", { exact: false }).fill("Nghiên cứu RAG");
    await page.getByLabel("Thẻ (tùy chọn)", { exact: true }).fill("AI, học máy");
    if (role === "teacher") await page.getByLabel("Thư mục (tùy chọn)", { exact: true }).selectOption(folderId);
    else {
      await expect(page.getByLabel("Thư mục (tùy chọn)", { exact: true })).toHaveCount(0);
      expect(state.requests.filter((request) => request.path === "/folders")).toHaveLength(0);
    }
    await page.getByRole("button", { name: "Tải lên", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Đã tải tài liệu lên" })).toBeVisible();
    await expect(page.getByText("Chờ xử lý", { exact: true })).toBeVisible();
    await expect(page.getByText("Hoàn tất", { exact: true })).toHaveCount(0);
    expect(state.uploads).toHaveLength(1);
    expect(state.uploads[0]).toContain('name="file"');
    expect(state.uploads[0]).toContain('name="title"');
    expect(state.uploads[0]).toContain("Nghiên cứu RAG");
    expect(state.uploads[0]).toContain('name="tags"');
    expect(state.uploads[0]).toContain("AI, học máy");
    expect(state.uploads[0].includes('name="folder_id"')).toBe(role === "teacher");
    expect(state.requests.some((request) => request.path === `/documents/${docId}`)).toBe(false);
    await expect(page.getByRole("link", { name: "Mở tài liệu", exact: true })).toHaveAttribute("href", `/documents/${docId}`);
    await page.getByRole("button", { name: "Tải tài liệu khác" }).click();
    await expect(page.getByLabel("Tiêu đề", { exact: false })).toHaveValue("");
    await expect(page.getByText(validFile.name, { exact: true })).toHaveCount(0);
    expect(state.unexpected).toEqual([]);
  });
}

test("file selection works with keyboard, cancellation retains file and remove is explicit", async ({ page }) => {
  await openUpload(page);
  const picker = page.waitForEvent("filechooser");
  await page.getByRole("button", { name: "Chọn tệp", exact: true }).focus();
  await page.keyboard.press("Enter");
  await (await picker).setFiles(validFile);
  await expect(page.getByText(validFile.name, { exact: true })).toBeVisible();
  await page.getByLabel("Tiêu đề", { exact: false }).fill("Bản nháp");
  await page.getByLabel("Tệp tài liệu", { exact: true }).setInputFiles([]);
  await expect(page.getByText(validFile.name, { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Bỏ tệp" }).click();
  await expect(page.getByText(validFile.name, { exact: true })).toHaveCount(0);
  await expect(page.getByLabel("Tiêu đề", { exact: false })).toHaveValue("Bản nháp");
});

for (const [name, mimeType, hex] of [
  ["sample.PDF", "application/pdf", "255044462d312e34"],
  ["sample.doc", "application/msword", "d0cf11e0a1b11ae1"],
  ["sample.docx", "application/octet-stream", "504b0304"],
  ["sample.pptx", "application/octet-stream", "504b0304"],
  ["sample.jpg", "image/jpeg", "ffd8ff"],
  ["sample.jpeg", "image/jpeg", "ffd8ff"],
  ["sample.png", "image/png", "89504e470d0a1a0a"],
]) {
  test("accepts extension and header validation for " + name, async ({ page }) => {
    await openUpload(page);
    await selectFile(page, { name, mimeType, buffer: Buffer.from(hex, "hex") });
    await expect(page.getByRole("main").getByRole("alert")).toHaveCount(0);
  });
}

test("required file, invalid extension, signature and oversized file are rejected", async ({ page }) => {
  const state = await openUpload(page);
  await page.getByRole("button", { name: "Tải lên", exact: true }).click();
  await expect(page.getByRole("main").getByRole("alert")).toContainText("Vui lòng chọn một tệp");
  await page.getByLabel("Tệp tài liệu", { exact: true }).setInputFiles({ name: "malware.exe", mimeType: "application/octet-stream", buffer: Buffer.from("x") });
  await expect(page.getByRole("main").getByRole("alert")).toContainText("Định dạng không được hỗ trợ");
  await page.getByLabel("Tệp tài liệu", { exact: true }).setInputFiles({ name: "fake.pdf", mimeType: "application/pdf", buffer: Buffer.from("renamed text") });
  await expect(page.getByRole("main").getByRole("alert")).toContainText("Nội dung tệp không khớp");
  // Create the oversized File in the browser, avoiding a 50 MiB fixture on disk.
  await page.getByTestId("upload-dropzone").evaluate((zone) => {
    const transfer = new DataTransfer();
    transfer.items.add(new File([new Uint8Array(50 * 1024 * 1024 + 1)], "large.txt", { type: "text/plain" }));
    zone.dispatchEvent(new DragEvent("drop", { bubbles: true, cancelable: true, dataTransfer: transfer }));
  });
  await expect(page.getByRole("main").getByRole("alert")).toContainText("50 MiB");
  expect(state.uploads).toHaveLength(0);
});

test("drag-drop accepts one valid file and rejects multiple without losing metadata", async ({ page }) => {
  await openUpload(page);
  await page.getByLabel("Tiêu đề", { exact: false }).fill("Nghiên cứu của tôi");
  await page.getByTestId("upload-dropzone").evaluate((zone) => {
    const transfer = new DataTransfer(); transfer.items.add(new File(["Nội dung"], "dragged.txt", { type: "text/plain" }));
    zone.dispatchEvent(new DragEvent("drop", { bubbles: true, cancelable: true, dataTransfer: transfer }));
  });
  await expect(page.getByText("dragged.txt", { exact: true })).toBeVisible();
  await page.getByTestId("upload-dropzone").evaluate((zone) => {
    const transfer = new DataTransfer(); transfer.items.add(new File(["a"], "a.txt")); transfer.items.add(new File(["b"], "b.txt"));
    zone.dispatchEvent(new DragEvent("drop", { bubbles: true, cancelable: true, dataTransfer: transfer }));
  });
  await expect(page.getByRole("main").getByRole("alert")).toContainText("Chỉ chọn một tệp");
  await expect(page.getByText("dragged.txt", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Tiêu đề", { exact: false })).toHaveValue("Nghiên cứu của tôi");
});

test("metadata constraints match storage and optional blank fields are omitted", async ({ page }) => {
  const state = await openUpload(page);
  await selectFile(page);
  await page.getByLabel("Tiêu đề", { exact: false }).fill("x".repeat(501));
  await page.getByLabel("Thẻ (tùy chọn)", { exact: true }).fill("y".repeat(101));
  await page.getByRole("button", { name: "Tải lên", exact: true }).click();
  await expect(page.getByLabel("Tiêu đề", { exact: false })).toHaveAttribute("aria-invalid", "true");
  await expect(page.getByLabel("Thẻ (tùy chọn)", { exact: true })).toHaveAttribute("aria-invalid", "true");
  expect(state.uploads).toHaveLength(0);
  await page.getByLabel("Tiêu đề", { exact: false }).fill("   ");
  await page.getByLabel("Thẻ (tùy chọn)", { exact: true }).fill("");
  await page.getByRole("button", { name: "Tải lên", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Đã tải tài liệu lên" })).toBeVisible();
  expect(state.uploads[0]).not.toContain('name="title"');
  expect(state.uploads[0]).not.toContain('name="tags"');
  expect(state.uploads[0]).not.toContain('name="folder_id"');
});

test("failed upload preserves file and all metadata for explicit retry", async ({ page }) => {
  const state = await openUpload(page); state.uploadStatus = 413;
  await selectFile(page);
  await page.getByLabel("Tiêu đề", { exact: false }).fill("Giữ nguyên tiêu đề");
  await page.getByLabel("Thẻ (tùy chọn)", { exact: true }).fill("AI, RAG");
  await page.getByLabel("Thư mục (tùy chọn)", { exact: true }).selectOption(folderId);
  await page.getByRole("button", { name: "Tải lên", exact: true }).click();
  await expect(page.getByRole("main").getByRole("alert")).toContainText("Tải lên chưa thành công");
  await expect(page.getByText(validFile.name, { exact: true })).toBeVisible();
  await expect(page.getByLabel("Tiêu đề", { exact: false })).toHaveValue("Giữ nguyên tiêu đề");
  await expect(page.getByLabel("Thẻ (tùy chọn)", { exact: true })).toHaveValue("AI, RAG");
  await expect(page.getByLabel("Thư mục (tùy chọn)", { exact: true })).toHaveValue(folderId);
  state.uploadStatus = 201;
  await page.getByRole("button", { name: "Thử tải lên lại" }).click();
  await expect(page.getByRole("heading", { name: "Đã tải tài liệu lên" })).toBeVisible();
  expect(state.uploads).toHaveLength(2);
});

for (const failure of [
  { status: 404, detail: "Thu muc khong ton tai hoac khong thuoc quyen quan ly cua ban", message: "Thu muc khong ton tai" },
  { status: 422, detail: [{ loc: ["body", "folder_id"], msg: "Input should be a valid UUID", type: "uuid_parsing" }], message: "Input should be a valid UUID" },
]) {
  test(`folder upload ${failure.status} preserves form and supports explicit retry`, async ({ page }) => {
    const state = await openUpload(page);
    state.uploadStatus = failure.status;
    state.uploadErrorDetail = failure.detail;
    await selectFile(page);
    await page.getByLabel("Tiêu đề", { exact: false }).fill("Giữ nguyên tài liệu");
    await page.getByLabel("Thẻ (tùy chọn)", { exact: true }).fill("AI, RAG");
    await page.getByLabel("Thư mục (tùy chọn)", { exact: true }).selectOption(folderId);
    await page.getByRole("button", { name: "Tải lên", exact: true }).click();
    await expect(page.getByRole("main").getByRole("alert")).toContainText(failure.message);
    await expect(page.getByText(validFile.name, { exact: true })).toBeVisible();
    await expect(page.getByLabel("Tiêu đề", { exact: false })).toHaveValue("Giữ nguyên tài liệu");
    await expect(page.getByLabel("Thẻ (tùy chọn)", { exact: true })).toHaveValue("AI, RAG");
    await expect(page.getByLabel("Thư mục (tùy chọn)", { exact: true })).toHaveValue(folderId);
    expect(state.uploads).toHaveLength(1);
    expect(state.uploads[0]).toContain(folderId);
    state.uploadStatus = 201;
    await page.getByRole("button", { name: "Thử tải lên lại" }).click();
    await expect(page.getByRole("heading", { name: "Đã tải tài liệu lên" })).toBeVisible();
    expect(state.uploads).toHaveLength(2);
    expect(state.unexpected).toEqual([]);
  });
}

test("in-flight upload is indeterminate, locked and cannot double-submit", async ({ page }) => {
  const state = await openUpload(page); state.holdUpload = true;
  try {
    await selectFile(page);
    await page.getByRole("button", { name: "Tải lên", exact: true }).evaluate((button) => { button.click(); button.click(); button.click(); });
    await expect.poll(() => state.uploads.length).toBe(1);
    await expect(page.getByRole("button", { name: "Đang gửi tài liệu…", exact: true })).toBeDisabled();
    await expect(page.getByRole("button", { name: "Bỏ tệp" })).toBeDisabled();
    await expect(page.getByLabel("Tiêu đề", { exact: false })).toBeDisabled();
    await expect(page.getByRole("progressbar")).toHaveCount(0);
    state.releaseUpload();
    await expect(page.getByRole("heading", { name: "Đã tải tài liệu lên" })).toBeVisible();
    expect(state.uploads).toHaveLength(1);
  } finally { state.releaseUpload(); }
});

test("folder failure does not block an upload without folder", async ({ page }) => {
  const state = await mockLibraryUpload(page); state.folderStatus = 503;
  await page.goto("/documents/upload");
  await expect(page.getByLabel("Thư mục (tùy chọn)", { exact: true })).toBeDisabled();
  await selectFile(page);
  await page.getByRole("button", { name: "Tải lên", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Đã tải tài liệu lên" })).toBeVisible();
  expect(state.uploads[0]).not.toContain('name="folder_id"');
});

for (const width of [320, 390, 768, 1024, 1440]) {
  test("upload responsive and long filename at " + width, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    await openUpload(page);
    await selectFile(page, { ...validFile, name: "TaiLieuNghienCuu".repeat(12) + ".txt" });
    await assertFits(page);
    await page.getByRole("button", { name: "Tải lên", exact: true }).focus();
    await expect(page.getByRole("button", { name: "Tải lên", exact: true })).toBeFocused();
    await assertFits(page);
  });
}

test("captures upload desktop, mobile and success", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1150 });
  await openUpload(page); await selectFile(page);
  await page.getByLabel("Tiêu đề", { exact: false }).fill("Nghiên cứu về Retrieval-Augmented Generation");
  await page.getByLabel("Thẻ (tùy chọn)", { exact: true }).fill("RAG, học máy, nghiên cứu");
  await page.getByLabel("Thư mục (tùy chọn)", { exact: true }).selectOption(folderId);
  await page.getByRole("main").evaluate((element) => { element.scrollTop = 0; });
  await page.screenshot({ path: test.info().outputPath("upload-desktop.png"), animations: "disabled" });
  await page.setViewportSize({ width: 390, height: 1000 });
  await page.screenshot({ path: test.info().outputPath("upload-mobile.png"), animations: "disabled" });
  await page.getByRole("button", { name: "Tải lên", exact: true }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: test.info().outputPath("upload-mobile-form.png"), animations: "disabled" });
  await page.getByRole("button", { name: "Tải lên", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Đã tải tài liệu lên" })).toBeVisible();
  await page.screenshot({ path: test.info().outputPath("upload-success.png"), animations: "disabled" });
});
