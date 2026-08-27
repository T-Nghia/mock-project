export type UserRole = "admin" | "teacher" | "student";

export type ProcessingStatus = "pending" | "processing" | "done" | "failed";

export interface User {
  id: string;
  full_name: string;
  email: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface UserPermissions {
  role: UserRole;
  permissions: string[];
}

export interface DocumentResponse {
  id: string;
  title: string;
  file_type: string;
  folder_id: string | null;
  uploaded_by: string;
  suggested_questions: string[];
  processing_status: ProcessingStatus;
  created_at: string;
}

export interface UploaderInfo {
  id: string;
  full_name: string;
}

export interface DocumentMetadata {
  id: string;
  title: string;
  file_type: string;
  file_size: number | null;
  folder_id: string | null;
  uploaded_by: UploaderInfo;
  summary: string | null;
  suggested_questions: string[];
  processing_status: ProcessingStatus;
  tags: string[];
  created_at: string;
}

export interface Folder {
  id: string;
  name: string;
  parent_folder_id: string | null;
  subject: string | null;
  owner_id: string;
  created_at: string;
}

export interface FolderTreeNode extends Folder {
  children: FolderTreeNode[];
}

export interface FolderDocument {
  id: string;
  title: string;
  file_path: string;
  file_type: string;
  folder_id: string | null;
  uploaded_by: string;
  summary: string | null;
  processing_status: string;
  created_at: string;
}

export interface DocumentSearchResult {
  id: string;
  title: string;
  file_type: string;
  summary: string | null;
  folder_id: string | null;
  folder_name: string | null;
  subject: string | null;
  tags: string[];
  uploaded_by: string;
  created_at: string;
}

export interface SearchPaginatedResponse {
  items: DocumentSearchResult[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface SearchParams {
  keyword?: string;
  title?: string;
  tags?: string[];
  subject?: string;
  folder_id?: string;
  page?: number;
  page_size?: number;
}

export interface ChartPoint {
  label: string;
  count: number;
}

export interface UploadChartPoint {
  date: string;
  count: number;
}

export interface DashboardSummary {
  total_documents: number;
  total_users?: number | null;
}

export interface DashboardCharts {
  uploads_by_day: UploadChartPoint[];
  documents_by_folder: ChartPoint[];
  users_by_role?: ChartPoint[] | null;
}

export interface DashboardResponse {
  role: UserRole;
  summary: DashboardSummary;
  charts: DashboardCharts;
}

export interface ApiErrorBody {
  detail?: string | { msg: string; loc?: (string | number)[] }[];
}

// ---------- Chat with Documents (RAG) ----------

export interface ChatCitation {
  chunk_id: string;
  chunk_index: number;
  quote: string;
  score: number;
  heading_path: string[];
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources: ChatCitation[];
  created_at: string;
}

export interface ChatSession {
  id: string;
  document_id: string;
  title: string;
  created_at: string;
}

export interface ChatSessionDetail extends ChatSession {
  messages: ChatMessage[];
}

export interface ChatAnswer {
  answer: string;
  sources: ChatCitation[];
}

// ---------- User Features: Bookmark / Comment / Rating ----------

export interface BookmarkStatus {
  document_id: string;
  bookmarked: boolean;
}

export interface BookmarkedDocument {
  id: string;
  title: string;
  file_type: string;
  processing_status: string;
  bookmarked_at: string;
}

export interface PaginatedBookmarks {
  items: BookmarkedDocument[];
  total: number;
  page: number;
  page_size: number;
}

export interface Comment {
  id: string;
  document_id: string;
  user_id: string;
  author_name: string;
  content: string;
  created_at: string;
}

export interface PaginatedComments {
  items: Comment[];
  total: number;
  page: number;
  page_size: number;
}

export interface RatingSummary {
  document_id: string;
  average: number | null;
  count: number;
  my_score: number | null;
}

// ---------- Forgot / Reset password ----------

export interface ForgotPasswordRequest {
  email: string;
}

export interface ResetPasswordRequest {
  token: string;
  new_password: string;
  confirm_new_password: string;
}
