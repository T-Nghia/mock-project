# Database Design — Sprint 1

PostgreSQL + extension `pgvector`. Nguồn sự thật (source of truth) của schema
là migration Alembic `backend/alembic/versions/530b2c170058_initial_schema.py`
— tài liệu này mô tả lại đúng nội dung migration đó, hiện là migration duy
nhất tính tới cuối Sprint 1.

## 1. ERD

```mermaid
erDiagram
    USERS ||--o{ FOLDERS : owns
    USERS ||--o{ DOCUMENTS : uploads
    USERS ||--o{ BOOKMARKS : creates
    USERS ||--o{ COMMENTS : writes
    USERS ||--o{ RATINGS : gives
    USERS ||--o{ CHAT_SESSIONS : starts
    USERS ||--o{ PASSWORD_RESET_TOKENS : requests

    FOLDERS ||--o{ FOLDERS : "parent_folder_id (subtree)"
    FOLDERS ||--o{ DOCUMENTS : contains

    DOCUMENTS ||--o{ DOCUMENT_CHUNKS : "split into"
    DOCUMENTS ||--o{ BOOKMARKS : "bookmarked in"
    DOCUMENTS ||--o{ COMMENTS : "commented on"
    DOCUMENTS ||--o{ RATINGS : "rated in"
    DOCUMENTS ||--o{ CHAT_SESSIONS : "asked about in"
    DOCUMENTS ||--o{ DOCUMENT_TAGS : tagged

    TAGS ||--o{ DOCUMENT_TAGS : "used in"

    CHAT_SESSIONS ||--o{ CHAT_MESSAGES : contains

    USERS {
        uuid id PK
        string full_name
        string email UK
        string hashed_password
        enum role "ADMIN | TEACHER | STUDENT"
        bool is_active
        datetime created_at
    }

    FOLDERS {
        uuid id PK
        string name
        uuid parent_folder_id FK "self, ON DELETE CASCADE"
        string subject "nullable"
        uuid owner_id FK "users.id"
        datetime created_at
    }

    DOCUMENTS {
        uuid id PK
        string title
        string file_path "path vật lý trên server"
        string file_type
        uuid folder_id FK "folders.id, ON DELETE SET NULL, nullable"
        uuid uploaded_by FK "users.id"
        text summary "nullable, do AI sinh ra"
        enum processing_status "PENDING|PROCESSING|DONE|FAILED"
        datetime created_at
    }

    DOCUMENT_CHUNKS {
        uuid id PK
        uuid document_id FK "documents.id, ON DELETE CASCADE"
        int chunk_index
        text content
        vector embedding "pgvector, dim=384, nullable"
        datetime created_at
    }

    TAGS {
        uuid id PK
        string name UK
    }

    DOCUMENT_TAGS {
        uuid document_id PK_FK "ON DELETE CASCADE"
        uuid tag_id PK_FK "ON DELETE CASCADE"
    }

    BOOKMARKS {
        uuid id PK
        uuid user_id FK "ON DELETE CASCADE"
        uuid document_id FK "ON DELETE CASCADE"
        datetime created_at
    }

    COMMENTS {
        uuid id PK
        uuid user_id FK "ON DELETE CASCADE"
        uuid document_id FK "ON DELETE CASCADE"
        text content
        datetime created_at
    }

    RATINGS {
        uuid id PK
        uuid user_id FK "ON DELETE CASCADE"
        uuid document_id FK "ON DELETE CASCADE"
        int score
        datetime created_at
    }

    CHAT_SESSIONS {
        uuid id PK
        uuid user_id FK "ON DELETE CASCADE"
        uuid document_id FK "ON DELETE SET NULL, nullable"
        string title
        datetime created_at
    }

    CHAT_MESSAGES {
        uuid id PK
        uuid session_id FK "chat_sessions.id, ON DELETE CASCADE"
        string role "user | assistant"
        text content
        json source_chunks "nullable, trích dẫn nguồn RAG"
        datetime created_at
    }

    PASSWORD_RESET_TOKENS {
        uuid id PK
        uuid user_id FK "users.id, ON DELETE CASCADE"
        string token_hash UK
        datetime expires_at
        datetime used_at "nullable"
        datetime created_at
    }
```

> `BOOKMARKS`, `COMMENTS`, `RATINGS`, `CHAT_SESSIONS`, `CHAT_MESSAGES` đã có
> bảng trong DB nhưng **chưa có API** phía trên (thuộc phạm vi Sprint 2 — AI
> Assistant & User Features).

## 2. Schema (chi tiết từng bảng)

### `users`
| Cột | Kiểu | Ràng buộc |
|---|---|---|
| id | UUID | PK |
| full_name | VARCHAR(255) | NOT NULL |
| email | VARCHAR(255) | NOT NULL, UNIQUE |
| hashed_password | VARCHAR(255) | NOT NULL |
| role | ENUM(`ADMIN`,`TEACHER`,`STUDENT`) | NOT NULL |
| is_active | BOOLEAN | NOT NULL |
| created_at | TIMESTAMPTZ | NOT NULL |

### `folders`
| Cột | Kiểu | Ràng buộc |
|---|---|---|
| id | UUID | PK |
| name | VARCHAR(255) | NOT NULL |
| parent_folder_id | UUID | FK → `folders.id`, ON DELETE CASCADE, nullable |
| subject | VARCHAR(255) | nullable |
| owner_id | UUID | FK → `users.id`, NOT NULL |
| created_at | TIMESTAMPTZ | NOT NULL |

> Không có UNIQUE constraint ở tầng DB cho cặp (`owner_id`, `parent_folder_id`,
> `name`) — việc chống trùng tên thư mục anh em hiện chỉ được validate ở tầng
> Service (`sibling_name_exists`), nên về lý thuyết có thể race-condition nếu 2
> request tạo folder trùng tên chạy đồng thời. Chấp nhận được ở quy mô mock
> project, nhưng nên thêm unique index ở Sprint 2 nếu triển khai multi-instance.

### `documents`
| Cột | Kiểu | Ràng buộc |
|---|---|---|
| id | UUID | PK |
| title | VARCHAR(500) | NOT NULL |
| file_path | VARCHAR(1000) | NOT NULL |
| file_type | VARCHAR(50) | NOT NULL |
| folder_id | UUID | FK → `folders.id`, ON DELETE SET NULL, nullable |
| uploaded_by | UUID | FK → `users.id`, NOT NULL |
| summary | TEXT | nullable |
| processing_status | ENUM(`PENDING`,`PROCESSING`,`DONE`,`FAILED`) | NOT NULL |
| created_at | TIMESTAMPTZ | NOT NULL |

> `file_size` (dung lượng) không phải cột riêng — được tính runtime từ file
> thật trên đĩa (xem `backend-design.md` mục Module Design > Document).

### `document_chunks`
| Cột | Kiểu | Ràng buộc |
|---|---|---|
| id | UUID | PK |
| document_id | UUID | FK → `documents.id`, ON DELETE CASCADE, NOT NULL |
| chunk_index | INTEGER | NOT NULL |
| content | TEXT | NOT NULL |
| embedding | VECTOR(384) (pgvector) | nullable |
| created_at | TIMESTAMPTZ | NOT NULL |

### `tags`
| Cột | Kiểu | Ràng buộc |
|---|---|---|
| id | UUID | PK |
| name | VARCHAR(100) | NOT NULL, UNIQUE |

### `document_tags` (bảng nối N-N)
| Cột | Kiểu | Ràng buộc |
|---|---|---|
| document_id | UUID | PK (composite), FK → `documents.id`, ON DELETE CASCADE |
| tag_id | UUID | PK (composite), FK → `tags.id`, ON DELETE CASCADE |

### `bookmarks`, `comments`, `ratings` (mẫu User Features — Sprint 2)
Chung mô típ: `id` (PK), `user_id` (FK → `users.id`, CASCADE), `document_id`
(FK → `documents.id`, CASCADE), `created_at`; `comments` có thêm `content`
(TEXT), `ratings` có thêm `score` (INTEGER).

### `chat_sessions` / `chat_messages` (AI Assistant — Sprint 2)
`chat_sessions`: `id`, `user_id` (FK CASCADE), `document_id` (FK SET NULL,
nullable), `title`, `created_at`.
`chat_messages`: `id`, `session_id` (FK → `chat_sessions.id`, CASCADE), `role`
(`user`/`assistant`), `content`, `source_chunks` (JSON, trích dẫn nguồn RAG),
`created_at`.

## 3. Index

Index hiện có (theo migration):

| Bảng | Index | Loại |
|---|---|---|
| `users` | `ix_users_email` trên `email` | UNIQUE |
| Tất cả bảng | Primary key trên `id` (hoặc composite PK cho `document_tags`) | UNIQUE (mặc định) |
| Tất cả FK | Index ngầm định do Postgres tạo cho FK constraint (tuỳ driver/version) | — |

Đề xuất bổ sung cho Sprint 2 (chưa có trong migration hiện tại — ảnh hưởng hiệu
năng khi dữ liệu lớn dần):

- `documents.uploaded_by` — phục vụ Dashboard (Teacher xem theo `owner_id`) và
  Search.
- `documents.folder_id` — phục vụ `GET /folders/{id}/documents` và Search theo
  `folder_id`.
- `folders.owner_id` — phục vụ mọi truy vấn `list_owned()`/`get_owned()`.
- `document_tags.tag_id` — hiện chỉ có composite PK bắt đầu bằng
  `document_id`, nên lookup theo chiều "tag → các document" (dùng trong Search
  theo `tags`) không tận dụng được index; nên thêm index riêng trên `tag_id`.
