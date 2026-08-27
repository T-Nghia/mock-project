import type {
  ApiErrorBody,
  BookmarkStatus,
  ChatAnswer,
  ChatSession,
  ChatSessionDetail,
  Comment,
  DashboardResponse,
  DocumentMetadata,
  DocumentResponse,
  Folder,
  FolderDocument,
  FolderTreeNode,
  PaginatedBookmarks,
  PaginatedComments,
  RatingSummary,
  SearchParams,
  SearchPaginatedResponse,
  TokenResponse,
  User,
  UserPermissions,
  UserRole,
} from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const ACCESS_KEY = "slrms_access_token";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

export const tokenStore = {
  getAccess(): string | null {
    if (typeof window === "undefined") return null;
    return localStorage.getItem(ACCESS_KEY);
  },
  set(tokens: TokenResponse) {
    localStorage.setItem(ACCESS_KEY, tokens.access_token);
  },
  clear() {
    localStorage.removeItem(ACCESS_KEY);
  },
};

async function parseErrorMessage(res: Response): Promise<string> {
  try {
    const body: ApiErrorBody = await res.json();
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail)) {
      return body.detail.map((d) => d.msg).join("; ");
    }
  } catch {
    // ignore, fall through
  }
  return `Lỗi ${res.status}`;
}

let refreshPromise: Promise<boolean> | null = null;

async function doRefresh(): Promise<boolean> {
  try {
    const res = await fetch(`${API_URL}/auth/refresh`, {
      method: "POST",
      credentials: "include",
    });
    if (!res.ok) {
      tokenStore.clear();
      return false;
    }
    const tokens: TokenResponse = await res.json();
    tokenStore.set(tokens);
    return true;
  } catch {
    return false;
  }
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  isForm?: boolean;
  auth?: boolean;
  query?: Record<string, string | number | boolean | string[] | undefined | null>;
}

function buildQuery(query?: RequestOptions["query"]): string {
  if (!query) return "";
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) {
      value.forEach((v) => params.append(key, v));
    } else {
      params.append(key, String(value));
    }
  }
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, isForm = false, auth = true, query } = options;

  const doFetch = async (): Promise<Response> => {
    const headers: Record<string, string> = {};
    if (!isForm && body !== undefined) headers["Content-Type"] = "application/json";
    if (auth) {
      const token = tokenStore.getAccess();
      if (token) headers["Authorization"] = `Bearer ${token}`;
    }
    return fetch(`${API_URL}${path}${buildQuery(query)}`, {
      method,
      headers,
      credentials: "include",
      body: isForm ? (body as FormData) : body !== undefined ? JSON.stringify(body) : undefined,
    });
  };

  let res = await doFetch();

  if (res.status === 401 && auth) {
    if (!refreshPromise) {
      refreshPromise = doRefresh().finally(() => {
        refreshPromise = null;
      });
    }
    const refreshed = await refreshPromise;
    if (refreshed) {
      res = await doFetch();
    }
  }

  if (!res.ok) {
    const message = await parseErrorMessage(res);
    throw new ApiError(res.status, message);
  }

  if (res.status === 204) return undefined as T;

  const contentType = res.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    return (await res.json()) as T;
  }
  return undefined as T;
}

// ---------- Auth ----------

export const authApi = {
  register(data: { full_name: string; email: string; password: string; confirm_password: string }) {
    return request<User>("/auth/register", { method: "POST", body: data, auth: false });
  },
  login(data: { email: string; password: string }) {
    return request<TokenResponse>("/auth/login", { method: "POST", body: data, auth: false });
  },
  refresh() {
    return doRefresh();
  },
  me() {
    return request<User>("/auth/me");
  },
  permissions() {
    return request<UserPermissions>("/auth/me/permissions");
  },
  logout() {
    return request<void>("/auth/logout", { method: "POST" });
  },
  createTeacher(data: { full_name: string; email: string; password: string }) {
    return request<User>("/auth/admin/teachers", { method: "POST", body: data });
  },
  listUsers() {
    return request<User[]>("/auth/admin/users");
  },
  updateUserRole(userId: string, role: UserRole) {
    return request<User>(`/auth/admin/users/${userId}/role`, { method: "PATCH", body: { role } });
  },
  updateUserStatus(userId: string, is_active: boolean) {
    return request<User>(`/auth/admin/users/${userId}/status`, {
      method: "PATCH",
      body: { is_active },
    });
  },
  forgotPassword(email: string) {
    return request<void>("/auth/forgot-password", { method: "POST", body: { email }, auth: false });
  },
  resetPassword(data: { token: string; new_password: string; confirm_new_password: string }) {
    return request<void>("/auth/reset-password", { method: "POST", body: data, auth: false });
  },
};

// ---------- Documents ----------

export const documentsApi = {
  upload(data: { file: File; title?: string; folder_id?: string; tags?: string }) {
    const form = new FormData();
    form.append("file", data.file);
    if (data.title) form.append("title", data.title);
    if (data.folder_id) form.append("folder_id", data.folder_id);
    if (data.tags) form.append("tags", data.tags);
    return request<DocumentResponse>("/documents/upload", { method: "POST", body: form, isForm: true });
  },
  getMetadata(documentId: string) {
    return request<DocumentMetadata>(`/documents/${documentId}`);
  },
  remove(documentId: string) {
    return request<void>(`/documents/${documentId}`, { method: "DELETE" });
  },
  async download(documentId: string): Promise<{ blob: Blob; filename: string }> {
    const token = tokenStore.getAccess();
    const res = await fetch(`${API_URL}/documents/${documentId}/download`, {
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    });
    if (!res.ok) throw new ApiError(res.status, await parseErrorMessage(res));
    const disposition = res.headers.get("content-disposition") ?? "";
    const match = disposition.match(/filename="?([^"]+)"?/);
    const filename = match?.[1] ?? "document";
    const blob = await res.blob();
    return { blob, filename };
  },
  async view(documentId: string): Promise<{ blob: Blob; contentType: string }> {
    const token = tokenStore.getAccess();
    const res = await fetch(`${API_URL}/documents/${documentId}/view`, {
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    });
    if (!res.ok) throw new ApiError(res.status, await parseErrorMessage(res));
    const contentType = res.headers.get("content-type") ?? "application/octet-stream";
    const blob = await res.blob();
    return { blob, contentType };
  },
};

// ---------- Folders ----------

export const foldersApi = {
  create(data: { name: string; parent_folder_id?: string | null; subject?: string | null }) {
    return request<Folder>("/folders", { method: "POST", body: data });
  },
  list() {
    return request<Folder[]>("/folders");
  },
  tree() {
    return request<FolderTreeNode[]>("/folders/tree");
  },
  get(folderId: string) {
    return request<Folder>(`/folders/${folderId}`);
  },
  update(folderId: string, data: { name?: string; parent_folder_id?: string | null; subject?: string | null }) {
    return request<Folder>(`/folders/${folderId}`, { method: "PATCH", body: data });
  },
  remove(folderId: string) {
    return request<void>(`/folders/${folderId}`, { method: "DELETE" });
  },
  documents(folderId: string, recursive = false) {
    return request<FolderDocument[]>(`/folders/${folderId}/documents`, { query: { recursive } });
  },
  moveDocument(documentId: string, folderId: string | null) {
    return request<FolderDocument>(`/folders/documents/${documentId}`, {
      method: "PATCH",
      body: { folder_id: folderId },
    });
  },
};

// ---------- Search ----------

export const searchApi = {
  search(params: SearchParams) {
    return request<SearchPaginatedResponse>("/search", { query: { ...params } });
  },
};

// ---------- Dashboard ----------

export const dashboardApi = {
  get() {
    return request<DashboardResponse>("/dashboard");
  },
};

// ---------- Chat with Documents (RAG) ----------

export const chatApi = {
  createSession(documentId: string) {
    return request<ChatSession>("/chat/sessions", { method: "POST", body: { document_id: documentId } });
  },
  listSessionsForDocument(documentId: string) {
    return request<ChatSession[]>(`/chat/documents/${documentId}/sessions`);
  },
  getSession(sessionId: string) {
    return request<ChatSessionDetail>(`/chat/sessions/${sessionId}`);
  },
  deleteSession(sessionId: string) {
    return request<void>(`/chat/sessions/${sessionId}`, { method: "DELETE" });
  },
  ask(sessionId: string, content: string) {
    return request<ChatAnswer>(`/chat/sessions/${sessionId}/messages`, { method: "POST", body: { content } });
  },
};

// ---------- User Features: Bookmark / Comment / Rating ----------

export const socialApi = {
  addBookmark(documentId: string) {
    return request<BookmarkStatus>(`/documents/${documentId}/bookmark`, { method: "POST" });
  },
  removeBookmark(documentId: string) {
    return request<BookmarkStatus>(`/documents/${documentId}/bookmark`, { method: "DELETE" });
  },
  getBookmarkStatus(documentId: string) {
    return request<BookmarkStatus>(`/documents/${documentId}/bookmark`);
  },
  listMyBookmarks(page = 1, page_size = 20) {
    return request<PaginatedBookmarks>("/me/bookmarks", { query: { page, page_size } });
  },
  addComment(documentId: string, content: string) {
    return request<Comment>(`/documents/${documentId}/comments`, { method: "POST", body: { content } });
  },
  listComments(documentId: string, page = 1, page_size = 20) {
    return request<PaginatedComments>(`/documents/${documentId}/comments`, { query: { page, page_size } });
  },
  deleteComment(commentId: string) {
    return request<void>(`/comments/${commentId}`, { method: "DELETE" });
  },
  setRating(documentId: string, score: number) {
    return request<RatingSummary>(`/documents/${documentId}/rating`, { method: "PUT", body: { score } });
  },
  removeRating(documentId: string) {
    return request<RatingSummary>(`/documents/${documentId}/rating`, { method: "DELETE" });
  },
  getRatingSummary(documentId: string) {
    return request<RatingSummary>(`/documents/${documentId}/rating`);
  },
};
