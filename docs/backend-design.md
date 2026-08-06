# Backend Design — Sprint 1

> Cập nhật cuối Sprint 1. Frontend Design chưa có trong tài liệu này — theo kế
> hoạch, Frontend bắt đầu từ Sprint 2.

## 1. Kiến trúc

Backend theo kiến trúc phân lớp (Layered Architecture), 1 chiều phụ thuộc từ trên
xuống:

```
Client (Swagger UI / Frontend Sprint 2)
        │  HTTP (JSON, multipart cho upload)
        ▼
┌───────────────────────────────────────────────┐
│  API Layer  (app/api/routers/*.py)             │  FastAPI routers, xác thực
│  - Nhận request, validate qua Pydantic schema  │  (JWT) & phân quyền (RBAC)
│  - Gọi Service tương ứng                       │  ở tầng này (Depends)
└───────────────────────────────────────────────┘
        ▼
┌───────────────────────────────────────────────┐
│  Service Layer  (app/services/*.py)            │  Business logic, validate
│  - Quy tắc nghiệp vụ, orchestration             │  nghiệp vụ, ném HTTPException
│  - Không biết gì về HTTP request/response       │  khi vi phạm business rule
└───────────────────────────────────────────────┘
        ▼
┌───────────────────────────────────────────────┐
│  Repository Layer  (app/repositories/*.py)     │  Truy vấn DB thuần
│  - Chỉ chứa câu lệnh SQLAlchemy (select/insert) │  (SQLAlchemy Core/ORM)
└───────────────────────────────────────────────┘
        ▼
┌───────────────────────────────────────────────┐
│  Model / Database Layer (app/models/*.py)      │  SQLAlchemy models
│  - PostgreSQL + pgvector (bảng document_chunks) │  + Alembic migrations
└───────────────────────────────────────────────┘
```

Thành phần hạ tầng đi kèm:

- **JWT (access + refresh token)** — `app/core/security.py`. Access token 15
  phút, refresh token 7 ngày, refresh token được lưu trong **Redis** theo key
  `refresh:{user_id}:{jti}` để hỗ trợ thu hồi (revoke) và nhiều phiên đăng nhập
  song song trên cùng một user.
- **RBAC (Role-Based Access Control)** — `app/core/permissions.py`. 3 role:
  `ADMIN`, `TEACHER`, `STUDENT`, mỗi role gắn với một tập `Permission`. Tầng API
  dùng `Depends(require_permission(...))` hoặc `Depends(require_role(...))` để
  chặn ở lối vào endpoint.
- **Background Tasks** — pipeline xử lý AI (extract text → chunk → embedding →
  tóm tắt) chạy nền bằng `BackgroundTasks` của FastAPI ngay sau khi upload xong,
  để endpoint upload trả kết quả ngay (status `pending`) thay vì chờ xử lý AI.
- **pgvector** — bảng `document_chunks.embedding` dùng kiểu `Vector(384)` để
  phục vụ tìm kiếm ngữ nghĩa cho AI Assistant (dự kiến hoàn thiện ở Sprint 2).
- **Alembic** — quản lý schema migration, chạy tự động (`alembic upgrade head`)
  trước khi backend khởi động (xem `docker-compose.yml`).

## 2. API Design

Tất cả response lỗi trả JSON dạng `{"detail": "..."}` theo chuẩn FastAPI.
Endpoint yêu cầu đăng nhập cần header `Authorization: Bearer <access_token>`.

### Auth (`/auth`)

| Method | Path | Quyền | Mô tả |
|---|---|---|---|
| POST | `/auth/register` | Public | Đăng ký tài khoản Student |
| POST | `/auth/login` | Public | Đăng nhập, trả access + refresh token |
| POST | `/auth/refresh` | Refresh token hợp lệ | Cấp access token mới, xoay vòng refresh token |
| GET | `/auth/me` | Đã đăng nhập | Thông tin tài khoản hiện tại |
| GET | `/auth/me/permissions` | Đã đăng nhập | Danh sách quyền của role hiện tại |
| POST | `/auth/logout` | Đã đăng nhập | Thu hồi refresh token (1 hoặc tất cả phiên) |
| POST | `/auth/admin/teachers` | Admin | Tạo tài khoản Teacher |
| GET | `/auth/admin/users` | Admin | Danh sách toàn bộ user |
| PATCH | `/auth/admin/users/{user_id}/role` | Admin | Đổi role |
| PATCH | `/auth/admin/users/{user_id}/status` | Admin | Khoá/mở tài khoản |

### Document (`/documents`)

| Method | Path | Quyền | Mô tả |
|---|---|---|---|
| POST | `/documents/upload` | `documents:create` (Admin, Teacher) | Upload tài liệu, xử lý AI chạy nền |
| GET | `/documents/{document_id}` | `documents:read` (mọi role) | Xem metadata: người upload, ngày tạo, dung lượng, loại file, trạng thái xử lý AI, tags |
| GET | `/documents/{document_id}/download` | `documents:read` (mọi role) | Tải file gốc về, tên file trả về theo `title` |

### Folder (`/folders`)

| Method | Path | Quyền | Mô tả |
|---|---|---|---|
| POST | `/folders` | Teacher | Tạo thư mục Môn học/Chủ đề |
| GET | `/folders` | Teacher | Danh sách phẳng thư mục của giáo viên |
| GET | `/folders/tree` | Teacher | Cây thư mục (Môn học → Chủ đề) |
| GET | `/folders/{folder_id}` | Teacher | Chi tiết 1 thư mục |
| PATCH | `/folders/{folder_id}` | Teacher | Đổi tên/môn học/vị trí |
| DELETE | `/folders/{folder_id}` | Teacher | Xoá đệ quy cây con, giữ lại tài liệu (gỡ khỏi thư mục) |
| GET | `/folders/{folder_id}/documents` | Teacher | Tài liệu trong thư mục (có tuỳ chọn `recursive`) |
| PATCH | `/folders/documents/{document_id}` | Teacher | Chuyển tài liệu vào/ra khỏi thư mục |

> **Ghi chú:** hiện tại toàn bộ `/folders/*` chỉ dành cho role Teacher (kể cả
> Admin cũng không thao tác được). Student chưa có endpoint riêng để duyệt cây
> thư mục — muốn tìm tài liệu, Student dùng `/search` (có filter theo
> `folder_id`).

### Search (`/search`)

| Method | Path | Quyền | Mô tả |
|---|---|---|---|
| GET | `/search` | Đã đăng nhập (mọi role) | Tìm tài liệu theo `keyword`/`title`/`tags`/`subject`/`folder_id`, có phân trang |

### Dashboard (`/dashboard`)

| Method | Path | Quyền | Mô tả |
|---|---|---|---|
| GET | `/dashboard` | Admin, Teacher (Student bị 403) | Admin: tổng số tài liệu/user + biểu đồ upload 7 ngày, tài liệu theo thư mục, user theo role. Teacher: chỉ số liệu tài liệu của chính mình |

## 3. Module Design

Mỗi module nghiệp vụ đi theo đúng 4 tầng (router → service → repository →
model), file tương ứng:

| Module | Router | Service | Repository | Model / Schema |
|---|---|---|---|---|
| Auth | `api/routers/auth.py` | `services/auth_service.py` | `repositories/user_repo.py` | `models/user.py`, `schemas/auth.py` |
| Document | `api/routers/documents.py` | `services/document_service.py` | `repositories/document_repo.py`, `repositories/tag_repo.py` | `models/document.py`, `schemas/document.py` |
| Folder | `api/routers/folders.py` | `services/folder_service.py` | `repositories/folder_repo.py` | `models/folder.py`, `schemas/folder.py` |
| Search | `api/routers/search.py` | `services/search_service.py` | `repositories/search_repo.py` | `schemas/search.py` |
| Dashboard | `api/routers/dashboard.py` | `services/dashboard_service.py` | `repositories/dashboard_repo.py` | `schemas/dashboard.py` |

Ghi chú thiết kế đáng chú ý theo module:

- **Document**: `DocumentService.save_upload()` chỉ lưu file + tạo record ở
  trạng thái `PENDING`, rồi đẩy `process_document_sync()` (extract → chunk →
  embed → summarize) vào `BackgroundTasks` để request trả về ngay. Response
  (`DocumentResponse`/`DocumentMetadataResponse`) chỉ trả các field cần thiết,
  **không** trả `file_path` tuyệt đối trên server ra ngoài. `file_size` không
  lưu cột riêng trong DB — được tính trực tiếp từ dung lượng file thật trên đĩa
  tại thời điểm gọi API, để luôn chính xác kể cả nếu file bị thay đổi thủ công.
- **Folder**: cây thư mục scope theo `owner_id` (mỗi Teacher có cây thư mục
  riêng). `subject` của thư mục con bắt buộc trùng thư mục cha (kế thừa hoặc
  validate khớp), việc đổi `subject`/di chuyển thư mục sẽ lan truyền xuống toàn
  bộ thư mục con (`propagate_subject`). Xoá thư mục là xoá đệ quy cây con nhưng
  **không xoá tài liệu** — tài liệu chỉ bị gỡ khỏi thư mục (`folder_id = NULL`).
- **Search**: 1 endpoint hợp nhất, hỗ trợ tìm theo từ khoá chung (OR trên
  title/tag/subject) hoặc lọc riêng từng field, có phân trang (`page`,
  `page_size`). Không giới hạn theo quyền sở hữu tài liệu — Student tìm được
  tài liệu của mọi Teacher.
- **Dashboard**: dữ liệu build tại thời điểm gọi API (không cache), Admin thấy
  toàn hệ thống, Teacher chỉ thấy số liệu tài liệu do chính mình upload.

### Việc còn thiếu (chuyển sang Sprint 2)

- Models `models/chat.py` (ChatSession/ChatMessage) và `models/social.py`
  (Bookmark/Comment/Rating) đã có sẵn bảng trong migration nhưng **chưa có
  router/service/repository** — đúng theo roadmap (AI Assistant + User
  Features nằm ở Sprint 2).
- Chưa có test cho module Search và cần rà lại toàn bộ error-handling khi tích
  hợp thật với Frontend ở Sprint 2.
