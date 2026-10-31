const { expect } = require("@playwright/test");
const folderId = "10000000-0000-4000-8000-000000000001";
const userId = "20000000-0000-4000-8000-000000000001";
const docId = "30000000-0000-4000-8000-000000000001";
const validFile = { name: "nghien-cuu.txt", mimeType: "text/plain", buffer: Buffer.from("Tài liệu nghiên cứu về RAG và học máy.") };

async function mockLibraryUpload(page, options = {}) {
  const role = options.role || "teacher";
  const user = { id: userId, role, full_name: "Nguyễn Minh Anh", email: "minhanh@example.com", is_active: true, created_at: "2026-10-20T08:00:00Z" };
  const names = ["Retrieval-Augmented Generation: Từ lý thuyết đến ứng dụng", "Nền tảng học máy và biểu diễn tri thức", "Thiết kế hệ thống tìm kiếm ngữ nghĩa"];
  const documents = Array.from({ length: 12 }, (_, index) => ({
    id: index === 0 ? docId : `30000000-0000-4000-8000-${String(index + 1).padStart(12, "0")}`,
    title: options.longData && index === 0 ? "TaiLieuNghienCuu".repeat(30) : names[index % 3] + (index > 2 ? ` — Phần ${index + 1}` : ""),
    file_type: index % 2 ? "pdf" : "txt", summary: "Các khái niệm nền tảng, phương pháp triển khai và ví dụ thực hành để hiểu sâu hơn về tài liệu.",
    folder_id: index % 2 ? null : folderId, folder_name: index % 2 ? null : "Nghiên cứu AI", subject: index % 2 ? null : "Trí tuệ nhân tạo",
    tags: ["học máy", "RAG"], uploaded_by: userId, created_at: `2026-10-${28 - index}T08:00:00Z`,
  }));
  let releaseSearch, releaseUpload;
  const searchGate = new Promise((resolve) => { releaseSearch = resolve; });
  const uploadGate = new Promise((resolve) => { releaseUpload = resolve; });
  const state = { role, documents: options.empty ? [] : documents, searches: [], requests: [], uploads: [], unexpected: [], searchStatus: 200, folderStatus: 200, uploadStatus: 201, holdSearch: false, holdUpload: false, releaseSearch, releaseUpload, slowSeen: false, slowCompleted: false };
  await page.route("http://localhost:8000/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const headers = { "access-control-allow-origin": new URL(process.env.APP_URL).origin, "access-control-allow-credentials": "true", "access-control-allow-headers": "authorization, content-type", "access-control-allow-methods": "GET, POST, DELETE, PUT, OPTIONS" };
    const respond = (body, status = 200) => route.fulfill({ status, headers, contentType: "application/json", body: JSON.stringify(body) });
    if (request.method() === "OPTIONS") return route.fulfill({ status: 204, headers });
    state.requests.push({ path, method: request.method() });
    if (path === "/auth/refresh") return respond({ access_token: "library-upload-test", token_type: "bearer" });
    if (path === "/auth/me") return respond(user);
    if (path === "/folders") {
      if (role !== "teacher") return respond({ detail: "Khong co quyen truy cap" }, 403);
      if (state.folderStatus !== 200) return respond({ detail: "Folders unavailable" }, state.folderStatus);
      return respond([{ id: folderId, name: "Nghiên cứu AI", subject: "Trí tuệ nhân tạo", parent_folder_id: null, owner_id: userId, created_at: user.created_at }]);
    }
    if (path === "/search") {
      const query = Object.fromEntries(url.searchParams);
      const tags = url.searchParams.getAll("tags");
      state.searches.push({ ...query, tags });
      if (state.holdSearch) await searchGate;
      if (state.searchStatus !== 200) return respond({ detail: "Search unavailable" }, state.searchStatus);
      if (query.keyword === "slow") { state.slowSeen = true; await new Promise((resolve) => setTimeout(resolve, 800)); }
      let items = state.documents.filter((doc) => {
        const matches = (value, part) => (value || "").toLocaleLowerCase().includes((part || "").trim().toLocaleLowerCase());
        return (!query.keyword || query.keyword === "slow" || [doc.title, doc.subject, ...doc.tags].some((value) => matches(value, query.keyword))) && (!query.subject || matches(doc.subject, query.subject)) && (!query.folder_id || doc.folder_id === query.folder_id) && (!tags.length || tags.some((tag) => doc.tags.some((value) => matches(value, tag))));
      });
      const total = items.length;
      const pageNumber = Number(query.page || 1);
      const pageSize = Number(query.page_size || 20);
      items = items.slice((pageNumber - 1) * pageSize, pageNumber * pageSize);
      // Current backend reports zero total/pages whenever the requested page is empty.
      await respond({ items, total: items.length ? total : 0, page: pageNumber, page_size: pageSize, total_pages: items.length ? Math.ceil(total / pageSize) : 0 });
      if (query.keyword === "slow") state.slowCompleted = true;
      return;
    }
    if (path === "/documents/upload") {
      state.uploads.push(request.postDataBuffer().toString("utf8"));
      if (state.holdUpload) await uploadGate;
      if (role === "student") return respond({ detail: "Khong co quyen truy cap" }, 403);
      if (state.uploadStatus !== 201) return respond({ detail: state.uploadErrorDetail ?? "Tệp chưa được chấp nhận. Vui lòng thử lại." }, state.uploadStatus);
      return respond({ id: docId, title: "Tài liệu nghiên cứu", file_type: "txt", folder_id: role === "teacher" ? folderId : null, uploaded_by: userId, suggested_questions: [], processing_status: "pending", created_at: user.created_at }, 201);
    }
    if (path === `/documents/${docId}`) return respond({ ...documents[0], uploaded_by: { id: userId, full_name: user.full_name }, file_size: 512, processing_status: "pending", suggested_questions: [] });
    if (path === `/documents/${docId}/view`) return route.fulfill({ headers, contentType: "text/plain", body: "Tài liệu nghiên cứu" });
    if (path.endsWith("/bookmark")) return respond({ document_id: docId, bookmarked: request.method() === "POST" });
    if (path.endsWith("/rating")) return respond({ document_id: docId, average: null, count: 0, my_score: null });
    if (path.endsWith("/comments")) return respond({ items: [], total: 0, page: 1, page_size: 50 });
    if (path === "/dashboard" && role === "student") return respond({ detail: "Dashboard is not available for students." }, 403);
    state.unexpected.push(path);
    return respond({ detail: "Unexpected request: " + path }, 404);
  });
  return state;
}
async function assertFits(page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect(await page.getByRole("main").evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);
}
module.exports = { mockLibraryUpload, assertFits, folderId, docId, validFile };
