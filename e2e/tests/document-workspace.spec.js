const { test, expect } = require("@playwright/test");

test.use({ channel: process.env.UI_BROWSER_CHANNEL || undefined, video: "off" });

const title = "Retrieval-Augmented Generation: Từ truy xuất đến câu trả lời";
const question = "RAG kết hợp truy xuất và sinh câu trả lời như thế nào?";
const answer = "RAG kết hợp hai bước: truy xuất các đoạn tài liệu liên quan, sau đó dùng ngữ cảnh này để tạo câu trả lời. Nguồn trích dẫn giúp người đọc đối chiếu thông tin với tài liệu gốc.";
const quote = "Bộ truy xuất chọn các đoạn văn phù hợp với câu hỏi và cung cấp chúng làm ngữ cảnh cho mô hình ngôn ngữ.";
const documentText = `RESEARCH NOTES / 01\n\nRetrieval-Augmented Generation\nKết nối mô hình ngôn ngữ với tri thức của bạn\n\n1. Tổng quan\n\nRetrieval-Augmented Generation (RAG) là phương pháp kết hợp khả năng truy xuất thông tin với khả năng sinh ngôn ngữ. Thay vì chỉ dựa vào kiến thức đã học, mô hình tham khảo các nguồn tài liệu liên quan để trả lời câu hỏi.\n\n2. Quy trình truy xuất\n\n${quote}\n\nTài liệu được chia thành các đoạn nhỏ và biểu diễn bằng vector. Khi nhận câu hỏi, hệ thống tìm kiếm các đoạn có nội dung gần nhất, sau đó đưa chúng vào ngữ cảnh của câu trả lời.\n\n3. Vai trò của nguồn trích dẫn\n\nNguồn trích dẫn giúp người đọc kiểm tra lại thông tin. Chất lượng câu trả lời phụ thuộc vào tài liệu, cách chia đoạn và độ phù hợp của kết quả truy xuất.\n\n4. Đánh giá hệ thống\n\nCần đánh giá đồng thời chất lượng truy xuất, mức độ bám sát nguồn và tính hữu ích của câu trả lời.`;

// A real, minimal one-page PDF fixture; no external renderer or package needed.
function pdfFixture() {
  const stream = "BT /F1 20 Tf 50 780 Td (Research notes: Retrieval-Augmented Generation) Tj 0 -40 Td /F1 12 Tf (Retrieve relevant evidence, then generate a grounded answer.) Tj ET";
  const objects = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>", "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>", "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>", `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`];
  let pdf = "%PDF-1.4\n";
  const offsets = [0];
  objects.forEach((object, index) => { offsets.push(Buffer.byteLength(pdf)); pdf += `${index + 1} 0 obj\n${object}\nendobj\n`; });
  const xref = Buffer.byteLength(pdf);
  pdf += `xref\n0 6\n0000000000 65535 f \n${offsets.slice(1).map((offset) => String(offset).padStart(10, "0") + " 00000 n \n").join("")}trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF`;
  return Buffer.from(pdf);
}

async function mockWorkspace(page, options = {}) {
  const state = { requests: [], creates: 0, asks: 0, sessions: options.existing ? ["s1", "s2"] : [], histories: {}, failAsk: !!options.failAsk, failList: !!options.failList, failView: !!options.failView, failMetadata: !!options.failMetadata, failCreate: !!options.failCreate, status: options.status || "done", unexpected: [] };
  const user = { id: "user-1", full_name: "Nguyễn Minh Anh", email: "minhanh@example.com", role: options.role || "teacher", is_active: true, created_at: "2026-10-20T08:00:00Z" };
  const session = (id) => ({ id, document_id: "doc-1", title: id === "s1" ? "Tổng quan về RAG" : id === "s2" ? "Đánh giá chất lượng" : "Cuộc trò chuyện mới", created_at: user.created_at });
  state.histories.s1 = [{ id: "old-1", role: "assistant", content: "Nội dung phiên tổng quan.", sources: [], created_at: user.created_at }];
  state.histories.s2 = [{ id: "old-2", role: "assistant", content: "Nội dung phiên đánh giá.", sources: [], created_at: user.created_at }];
  let bookmarked = false;
  let score = null;
  let comments = [];
  await page.route("http://localhost:8000/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const method = request.method();
    const headers = { "access-control-allow-origin": new URL(process.env.APP_URL).origin, "access-control-allow-credentials": "true", "access-control-allow-headers": "authorization, content-type", "access-control-allow-methods": "GET, POST, PUT, DELETE, OPTIONS", "access-control-expose-headers": "content-disposition" };
    const respond = (body, status = 200) => route.fulfill({ status, headers, contentType: "application/json", body: JSON.stringify(body) });
    if (method === "OPTIONS") return route.fulfill({ status: 204, headers });
    state.requests.push({ path, method, body: request.postDataJSON() });
    if (path === "/auth/refresh") return respond({ access_token: "workspace-test-token", token_type: "bearer" });
    if (path === "/auth/me") return respond(user);
    if (path === "/documents/doc-1") {
      if (method === "DELETE") return route.fulfill({ status: 204, headers });
      if (state.failMetadata) return respond({ detail: "Không tải được thông tin tài liệu." }, 503);
      return respond({ id: "doc-1", title, file_type: options.fileType || "txt", file_size: 48200, folder_id: null, uploaded_by: { id: options.otherOwner ? "other-user" : user.id, full_name: user.full_name }, summary: "Tìm hiểu kiến trúc RAG, vai trò của truy xuất và cách kiểm chứng câu trả lời qua nguồn trích dẫn.", suggested_questions: [question, "Nguồn trích dẫn có vai trò gì?", "Những yếu tố nào ảnh hưởng đến chất lượng RAG?"], processing_status: state.status, tags: ["LLM", "RAG", "Nghiên cứu"], created_at: user.created_at });
    }
    if (path === "/documents/doc-1/view" || path === "/documents/doc-1/download") {
      if (state.failView && path.endsWith("/view")) return respond({ detail: "Không tải được nội dung." }, 503);
      return route.fulfill({ status: 200, headers: { ...headers, "content-disposition": 'attachment; filename="research-notes.txt"' }, contentType: options.fileType === "pdf" ? "application/pdf" : "text/plain", body: options.fileType === "pdf" ? pdfFixture() : documentText });
    }
    if (path === "/documents/doc-1/bookmark") {
      if (method !== "GET") bookmarked = method === "POST";
      return respond({ document_id: "doc-1", bookmarked });
    }
    if (path === "/documents/doc-1/rating") {
      if (method === "PUT") score = request.postDataJSON().score;
      if (method === "DELETE") score = null;
      return respond({ document_id: "doc-1", average: score, count: score ? 1 : 0, my_score: score });
    }
    if (path === "/documents/doc-1/comments") {
      if (method === "POST") {
        const comment = { id: "comment-1", document_id: "doc-1", user_id: user.id, author_name: user.full_name, content: request.postDataJSON().content, created_at: user.created_at };
        comments.push(comment);
        return respond(comment, 201);
      }
      return respond({ items: comments, total: comments.length, page: 1, page_size: 50 });
    }
    if (path === "/comments/comment-1" && method === "DELETE") { comments = []; return route.fulfill({ status: 204, headers }); }
    if (path === "/chat/documents/doc-1/sessions") return state.failList ? respond({ detail: "Lịch sử tạm thời không khả dụng." }, 503) : respond(state.sessions.map(session));
    if (path === "/chat/sessions" && method === "POST") {
      state.creates++;
      if (options.delay) await new Promise((resolve) => setTimeout(resolve, options.delay));
      if (state.failCreate) return respond({ detail: "Không tạo được phiên." }, 503);
      const id = "new-" + state.creates;
      state.sessions.unshift(id);
      state.histories[id] = [];
      return respond(session(id), 201);
    }
    const match = path.match(/^\/chat\/sessions\/([^/]+)(\/messages)?$/);
    if (match) {
      const id = match[1];
      if (match[2]) {
        state.asks++;
        if (options.delay) await new Promise((resolve) => setTimeout(resolve, options.delay));
        if (state.failAsk) return respond({ detail: "Dịch vụ AI tạm thời không khả dụng." }, 503);
        const sources = [{ chunk_id: "chunk-1", chunk_index: 1, quote, score: 0.87, heading_path: ["RAG", "Quy trình truy xuất"] }];
        state.histories[id].push({ id: "q-" + state.asks, role: "user", content: request.postDataJSON().content, sources: [], created_at: user.created_at }, { id: "a-" + state.asks, role: "assistant", content: answer, sources, created_at: user.created_at });
        return respond({ answer, sources }, 201);
      }
      if (method === "DELETE") { state.sessions = state.sessions.filter((value) => value !== id); return route.fulfill({ status: 204, headers }); }
      return respond({ ...session(id), messages: state.histories[id] || [] });
    }
    if (path === "/search") return respond({ items: [], total: 0, page: 1, page_size: 10, total_pages: 0 });
    state.unexpected.push({ path, method });
    return respond({ detail: "Unexpected request" }, 404);
  });
  return state;
}

async function openWorkspace(page, options = {}) {
  await page.setViewportSize({ width: 1440, height: 960 });
  const state = await mockWorkspace(page, options);
  await page.goto("/documents/doc-1");
  await expect(page.getByRole("heading", { name: title, exact: true })).toBeVisible();
  if (!options.failList && (!options.status || options.status === "done")) await expect(page.getByLabel("Câu hỏi cho trợ lý AI")).toBeEnabled();
  return state;
}

async function assertFits(page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect(await page.getByRole("main").evaluate((element) => element.scrollHeight <= element.clientHeight + 1)).toBe(true);
}

// Captures uncaught UI errors independently of the assertions in each case.
let pageErrors;
test.beforeEach(async ({ page }) => { pageErrors = []; page.on("pageerror", (error) => pageErrors.push(error.message)); });
test.afterEach(() => expect(pageErrors).toEqual([]));

test("opens reader without creating sessions; desktop 60/40 layout and download", async ({ page }) => {
  const state = await openWorkspace(page);
  await expect(page.getByText(documentText, { exact: true })).toBeVisible();
  const left = await page.getByRole("tabpanel", { name: "Tài liệu", exact: true }).boundingBox();
  const right = await page.getByRole("tabpanel", { name: "Trợ lý AI", exact: true }).boundingBox();
  expect(left.width / right.width).toBeCloseTo(1.5, 1);
  expect(state.creates).toBe(0);
  await page.getByRole("button", { name: /Lịch sử/ }).click();
  await expect(page.getByText("Chưa có cuộc trò chuyện nào.")).toBeVisible();
  await page.keyboard.press("Escape");
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Tải xuống tài liệu" }).click();
  expect((await download).suggestedFilename()).toBe("research-notes.txt");
  await assertFits(page);
  expect(state.unexpected).toEqual([]);
});

test("first question creates one session, renders answer and honest citations", async ({ page }) => {
  const state = await openWorkspace(page, { delay: 200 });
  await page.getByRole("button", { name: question, exact: true }).click();
  await expect(page.getByText("Đang tìm câu trả lời…")).toBeVisible();
  await expect(page.getByRole("button", { name: "Cuộc trò chuyện mới", exact: true })).toBeDisabled();
  await expect(page.getByText(answer, { exact: true })).toBeVisible();
  const source = page.locator("summary", { hasText: "Quy trình truy xuất" });
  await source.click();
  await expect(page.getByRole("blockquote")).toHaveText(quote);
  await expect(page.getByText("87%", { exact: true })).toHaveCount(0);
  expect(state.creates).toBe(1);
  expect(state.asks).toBe(1);
  await page.screenshot({ path: test.info().outputPath("workspace-desktop.png"), fullPage: true, animations: "disabled" });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("tab", { name: "Trợ lý AI", exact: true }).click();
  await page.getByRole("blockquote").scrollIntoViewIfNeeded();
  await page.screenshot({ path: test.info().outputPath("workspace-mobile-chat.png"), fullPage: true, animations: "disabled" });
  await page.getByRole("tab", { name: "Tài liệu", exact: true }).click();
  await page.screenshot({ path: test.info().outputPath("workspace-mobile-document.png"), fullPage: true, animations: "disabled" });
});

test("mobile tabs, sidebar and viewport changes preserve draft and active session", async ({ page }) => {
  const state = await openWorkspace(page, { existing: true });
  const input = page.getByLabel("Câu hỏi cho trợ lý AI");
  await input.fill("Bản nháp cần giữ nguyên");
  for (const width of [320, 768, 1024]) {
    await page.setViewportSize({ width, height: 900 });
    await page.getByRole("tab", { name: "Trợ lý AI", exact: true }).click();
    await expect(input).toHaveValue("Bản nháp cần giữ nguyên");
    await expect(page.getByText("Nội dung phiên tổng quan.", { exact: true })).toBeVisible();
    await assertFits(page);
    await page.getByRole("tab", { name: "Tài liệu", exact: true }).click();
    await page.getByRole("tab", { name: "Thông tin & thảo luận" }).click();
    await assertFits(page);
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.getByRole("button", { name: "Thu gọn thanh điều hướng", exact: true }).click();
  await expect(input).toHaveValue("Bản nháp cần giữ nguyên");
  expect(state.creates).toBe(0);
  expect(state.requests.filter((request) => request.path === "/chat/sessions/s1")).toHaveLength(1);
});

test("switches history and restores a draft per session", async ({ page }) => {
  const state = await openWorkspace(page, { existing: true });
  const input = page.getByLabel("Câu hỏi cho trợ lý AI");
  await input.fill("Bản nháp tổng quan");
  await page.getByRole("button", { name: /Lịch sử/ }).click();
  const history = page.getByRole("dialog", { name: /Lịch sử/ });
  await history.getByRole("button", { name: /^Đánh giá chất lượng/ }).click();
  await expect(page.getByText("Nội dung phiên đánh giá.", { exact: true })).toBeVisible();
  await input.fill("Bản nháp đánh giá");
  await page.getByRole("button", { name: /Lịch sử/ }).click();
  await history.getByRole("button", { name: /^Tổng quan về RAG/ }).click();
  await expect(input).toHaveValue("Bản nháp tổng quan");
  expect(state.creates).toBe(0);
});

test("rapid new-session clicks create once; deleting the last session never recreates it", async ({ page }) => {
  const state = await openWorkspace(page, { delay: 300 });
  await page.getByRole("button", { name: "Cuộc trò chuyện mới", exact: true }).evaluate((button) => { button.click(); button.click(); button.click(); });
  await expect.poll(() => state.sessions.length).toBe(1);
  await expect(page.getByLabel("Câu hỏi cho trợ lý AI")).toBeEnabled();
  expect(state.creates).toBe(1);
  await page.getByRole("button", { name: /Lịch sử/ }).click();
  await page.getByRole("button", { name: /^Xóa cuộc trò chuyện/ }).click();
  await expect(page.getByText("Chưa có cuộc trò chuyện nào.")).toBeVisible();
  expect(state.sessions).toHaveLength(0);
  expect(state.creates).toBe(1);
});

test("failed answer retains question and retries in the same session", async ({ page }) => {
  const state = await openWorkspace(page, { failAsk: true });
  const input = page.getByLabel("Câu hỏi cho trợ lý AI");
  await input.fill(question);
  await input.press("Enter");
  await expect(input).toHaveValue(question);
  await expect(page.getByRole("tabpanel", { name: "Trợ lý AI", exact: true }).getByRole("alert")).toContainText("Không lấy được câu trả lời");
  state.failAsk = false;
  await input.press("Enter");
  await expect(page.getByText(answer, { exact: true })).toBeVisible();
  expect(state.creates).toBe(1);
  expect(state.asks).toBe(2);
});

test("initial history and creation failures are recoverable without automatic POSTs", async ({ page }) => {
  const state = await openWorkspace(page, { failList: true, failCreate: true });
  await expect(page.getByRole("button", { name: "Thử lại lịch sử" })).toBeVisible();
  await expect(page.getByLabel("Câu hỏi cho trợ lý AI")).toBeDisabled();
  expect(state.creates).toBe(0);
  state.failList = false;
  await page.getByRole("button", { name: "Thử lại lịch sử" }).click();
  await page.getByLabel("Câu hỏi cho trợ lý AI").fill(question);
  await page.getByRole("button", { name: "Gửi câu hỏi", exact: true }).click();
  await expect(page.getByRole("tabpanel", { name: "Trợ lý AI", exact: true }).getByRole("alert")).toContainText("Không tạo được phiên");
  await expect(page.getByLabel("Câu hỏi cho trợ lý AI")).toHaveValue(question);
  expect(state.asks).toBe(0);
  state.failCreate = false;
  await page.getByRole("button", { name: "Gửi câu hỏi", exact: true }).click();
  await expect(page.getByText(answer, { exact: true })).toBeVisible();
  expect(state.sessions).toHaveLength(1);
});

test("bookmark, rating, comments and owner delete keep their API contracts", async ({ page }) => {
  const state = await openWorkspace(page);
  await page.getByRole("tab", { name: "Thông tin & thảo luận" }).click();
  await page.getByRole("button", { name: "Lưu tài liệu", exact: true }).click();
  await expect(page.getByRole("button", { name: "Đã lưu", exact: true })).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "Đã lưu", exact: true }).click();
  await page.getByRole("button", { name: "Đánh giá 5 sao" }).click();
  await expect(page.getByText("5.0 (1 đánh giá)")).toBeVisible();
  await page.getByRole("button", { name: "Đánh giá 5 sao" }).click();
  await expect(page.getByText("Chưa có đánh giá")).toBeVisible();
  await page.getByLabel("Bình luận về tài liệu").fill("Tài liệu hữu ích cho nghiên cứu.");
  await page.getByRole("button", { name: "Gửi bình luận", exact: true }).click();
  await expect(page.getByText("Tài liệu hữu ích cho nghiên cứu.", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Xoá bình luận" }).click();
  await expect(page.getByText("Tài liệu hữu ích cho nghiên cứu.", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Xóa", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "Xóa tài liệu?" })).toBeVisible();
  await page.getByRole("button", { name: "Hủy", exact: true }).click();
  expect(state.requests.some((request) => request.path === "/documents/doc-1" && request.method === "DELETE")).toBe(false);
  expect(state.requests).toEqual(expect.arrayContaining([
    expect.objectContaining({ path: "/documents/doc-1/bookmark", method: "POST" }),
    expect.objectContaining({ path: "/documents/doc-1/bookmark", method: "DELETE" }),
    expect.objectContaining({ path: "/documents/doc-1/rating", method: "PUT", body: { score: 5 } }),
    expect.objectContaining({ path: "/documents/doc-1/rating", method: "DELETE" }),
    expect.objectContaining({ path: "/documents/doc-1/comments", method: "POST", body: { content: "Tài liệu hữu ích cho nghiên cứu." } }),
    expect.objectContaining({ path: "/comments/comment-1", method: "DELETE" }),
  ]));
  expect(state.unexpected).toEqual([]);
});

for (const role of ["student", "teacher", "admin"]) {
  test("document delete permission is preserved for " + role, async ({ page }) => {
    await openWorkspace(page, { role, otherOwner: true });
    await page.getByRole("tab", { name: "Thông tin & thảo luận" }).click();
    await expect(page.getByRole("button", { name: "Xóa", exact: true })).toHaveCount(role === "admin" ? 1 : 0);
  });
}

for (const status of ["processing", "failed"]) {
  test("unprocessed document remains readable without chat requests: " + status, async ({ page }) => {
    const state = await openWorkspace(page, { status });
    await expect(page.getByText("Trợ lý AI chưa sẵn sàng")).toBeVisible();
    expect(state.requests.filter((request) => request.path.startsWith("/chat/"))).toHaveLength(0);
    state.status = "done";
    await page.getByRole("button", { name: "Kiểm tra lại" }).click();
    await expect(page.getByLabel("Câu hỏi cho trợ lý AI")).toBeEnabled();
    expect(state.creates).toBe(0);
  });
}

test("PDF is shown in the existing iframe and survives tab changes", async ({ page }) => {
  const state = await openWorkspace(page, { fileType: "pdf" });
  const frame = page.getByTitle("Xem tài liệu PDF", { exact: true });
  await expect(frame).toHaveAttribute("src", /^blob:/);
  const src = await frame.getAttribute("src");
  await page.getByRole("tab", { name: "Thông tin & thảo luận" }).click();
  await page.getByRole("tab", { name: "Đọc tài liệu", exact: true }).click();
  await expect(frame).toHaveAttribute("src", src);
  const bounds = await frame.boundingBox();
  expect(bounds.height).toBeGreaterThan(400);
  expect(state.creates).toBe(0);
});

test("viewer error retries and unsupported format keeps download", async ({ page }) => {
  const state = await openWorkspace(page, { failView: true });
  await expect(page.getByRole("button", { name: "Thử tải lại" })).toBeVisible();
  state.failView = false;
  await page.getByRole("button", { name: "Thử tải lại" }).click();
  await expect(page.getByText(documentText, { exact: true })).toBeVisible();
  await page.unrouteAll();
  await mockWorkspace(page, { fileType: "docx" });
  await page.reload();
  await expect(page.getByText(/Định dạng .docx chưa hỗ trợ/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Tải xuống", exact: true })).toBeEnabled();
});

test("metadata error retry and mobile keyboard tab navigation", async ({ page }) => {
  const state = await mockWorkspace(page, { failMetadata: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/documents/doc-1");
  await expect(page.getByRole("main").getByRole("alert")).toContainText("Không tải được thông tin tài liệu.");
  state.failMetadata = false;
  await page.getByRole("button", { name: "Thử lại", exact: true }).click();
  const docTab = page.getByRole("tab", { name: "Tài liệu", exact: true });
  await docTab.focus();
  await page.keyboard.press("ArrowRight");
  const aiTab = page.getByRole("tab", { name: "Trợ lý AI", exact: true });
  await expect(aiTab).toBeFocused();
  await expect(aiTab).toHaveAttribute("aria-selected", "true");
  await expect(page.getByLabel("Câu hỏi cho trợ lý AI")).toBeEnabled();
  await page.keyboard.press("Home");
  await expect(docTab).toBeFocused();
  expect(state.creates).toBe(0);
});

test("sending survives mobile tab changes and repeated submissions without duplicate sessions", async ({ page }) => {
  const state = await openWorkspace(page, { delay: 500 });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("tab", { name: "Trợ lý AI", exact: true }).click();
  const input = page.getByLabel("Câu hỏi cho trợ lý AI");
  await input.fill(question);
  await page.getByRole("button", { name: "Gửi câu hỏi", exact: true }).evaluate((button) => { button.click(); button.click(); });
  await page.getByRole("tab", { name: "Tài liệu", exact: true }).click();
  await expect.poll(() => state.asks).toBe(1);
  await page.getByRole("tab", { name: "Trợ lý AI", exact: true }).click();
  await expect(page.getByText(answer, { exact: true })).toBeVisible();
  expect(state.creates).toBe(1);
  expect(state.asks).toBe(1);
  await input.fill("Dòng thứ nhất");
  await input.press("Shift+Enter");
  await input.pressSequentially("Dòng thứ hai");
  await expect(input).toHaveValue("Dòng thứ nhất\nDòng thứ hai");
  expect(state.asks).toBe(1);
});

test("explicit new conversation preserves existing histories and deletes active session safely", async ({ page }) => {
  const state = await openWorkspace(page, { existing: true });
  await page.getByRole("button", { name: "Cuộc trò chuyện mới", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Hiểu sâu hơn, từng câu hỏi" })).toBeVisible();
  expect(state.creates).toBe(1);
  await page.getByRole("button", { name: /Lịch sử/ }).click();
  const history = page.getByRole("dialog", { name: /Lịch sử/ });
  await expect(history.getByRole("button", { name: /^Tổng quan về RAG/ })).toBeVisible();
  await expect(history.getByRole("button", { name: /^Đánh giá chất lượng/ })).toBeVisible();
  await history.getByRole("button", { name: "Xóa cuộc trò chuyện Cuộc trò chuyện mới", exact: true }).click();
  await expect(page.getByText("Nội dung phiên tổng quan.", { exact: true })).toBeVisible();
  expect(state.sessions).toEqual(["s1", "s2"]);
  expect(state.creates).toBe(1);
});
