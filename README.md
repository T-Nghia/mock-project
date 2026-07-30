# Smart Learning Resource Management System

Nền tảng Quản lý Tài liệu Học tập Thông minh — base project

## 1. Kiến trúc

Layered Architecture, tách 4 lớp như đặc tả mục 3.1:

```
API Layer (FastAPI routers)  →  Service Layer  →  Repository Layer  →  Database (PostgreSQL + pgvector)
```

```
.
├── docker-compose.yml
├── .env / .env.example
├── db/init.sql               # bật extension pgvector khi Postgres khởi tạo lần đầu
├── backend/                  # FastAPI (Python)
│   ├── alembic.ini
│   ├── alembic/
│   │   ├── env.py            # lấy DATABASE_URL & Base.metadata trực tiếp từ app
│   │   └── versions/
│   │       └── ..._initial_schema.py   # migration đầu tiên, đã test upgrade+downgrade thật
│   └── app/
│       ├── core/             # config, database session, JWT/bcrypt
│       ├── models/           # SQLAlchemy models (users, folders, documents, ...)
│       ├── schemas/          # Pydantic request/response
│       ├── repositories/     # truy vấn DB thuần (Repository Pattern)
│       ├── services/         # business logic (auth, document, search, dashboard, AI)
│       ├── api/routers/      # FastAPI endpoints + phân quyền theo role
│       ├── worker/           # Celery app + task xử lý tài liệu nền
│       ├── utils/            # extract text / chunk / summary / embedding
│       ├── seed.py           # tạo tài khoản Admin mặc định
│       └── main.py
└── frontend/                 # Next.js (App Router) — login, dashboard, documents
```

## 2. Công nghệ

| Hạng mục | Công nghệ |
|---|---|
| Backend | FastAPI, SQLAlchemy 2.0, Pydantic v2 |
| Database | PostgreSQL 16 + pgvector (vector search cho RAG) |
| Auth | JWT (python-jose) + bcrypt (passlib) |
| Async job | Celery + Redis (xử lý OCR/chunk/embedding nền, không block upload) |
| AI/RAG | Retrieval nội bộ (cosine similarity trên `document_chunks.embedding`) — xem mục 5 |
| Frontend | Next.js 14, App Router, TypeScript |
| Containerization | Docker + Docker Compose |

## 3. Chạy project

```bash
git clone <repo>   # hoặc giải nén file zip đã tải
cd smart-learning-rms

cp .env.example .env    # (đã có sẵn .env mẫu, có thể sửa JWT_SECRET_KEY...)

docker compose up --build
```

`docker compose up` sẽ tự chạy service `migrate` (áp dụng toàn bộ Alembic migrations — tạo extension
`pgvector` + 11 bảng) trước khi `backend` và `worker` khởi động; bạn sẽ thấy log `slrms-migrate exited
with code 0` rồi mới đến `slrms-backend`/`slrms-worker` chạy. Không cần chạy migration thủ công.

Sau khi tất cả container chạy (lần đầu build ~2-3 phút):

- Backend API: http://localhost:8000  — Swagger UI: http://localhost:8000/docs
- Frontend: http://localhost:3000
- PostgreSQL: localhost:5432 (user/pass trong `.env`)
- Redis: localhost:6379

Tạo tài khoản Admin mặc định (chỉ cần chạy 1 lần):

```bash
docker compose exec backend python -m app.seed
# Created admin: admin@slrms.local / Admin@123
```

Đăng nhập ở http://localhost:3000/login bằng tài khoản trên, hoặc `/register` để tạo tài khoản Student.
Để có tài khoản Teacher, Admin cần cập nhật `role` trực tiếp trong DB (hoặc bổ sung API "tạo Teacher" — xem mục 6).

Dừng project: `docker compose down` (thêm `-v` nếu muốn xoá luôn dữ liệu Postgres/uploads).

## 4. Các module đã triển khai (theo đặc tả)

| Module | Trạng thái trong base project |

## 5. Vì sao AI Assistant chạy được mà không cần API key?

`app/utils/text_extract.py::embed_text()` dùng một "pseudo-embedding" xác định (hash từng từ vào vector 384 chiều)
— đủ để pipeline pgvector + retrieval hoạt động thật (upload → Celery chunk & embed → chat hỏi đáp trả lời trích dẫn
đúng chunk liên quan), nhưng không "hiểu" ngữ nghĩa như embedding thật. Đây là lựa chọn có chủ đích để:

1. Base project chạy được ngay bằng `docker compose up`, không phụ thuộc key ngoài.
2. Đúng roadmap Sprint 2 (đặc tả mục Roadmap): nhóm cắm LLM thật vào sau khi Sprint 1 ổn định.

Khi có `OPENAI_API_KEY`/`ANTHROPIC_API_KEY`, sửa 2 chỗ:
- `embed_text()` → gọi API embedding thật.
- `AIService.ask()` trong `ai_service.py` → gọi Chat Completion với `context` đã retrieve, thay vì trả nguyên văn.

## 6. Testing

```bash
# Vào container backend rồi cài thêm pytest (đã có sẵn nếu bổ sung vào requirements.txt)
docker compose exec backend pip install pytest pytest-cov httpx
docker compose exec backend pytest
```

Gợi ý cấu trúc: `backend/tests/unit/` (test service/repository riêng lẻ), `backend/tests/api/`
(test endpoint qua `TestClient`), `backend/tests/integration/` (đăng ký → đăng nhập → upload → chat).

## 7. Database migrations (Alembic)

Schema được quản lý hoàn toàn bằng Alembic (không còn dùng `Base.metadata.create_all()`).
Migration đầu tiên (`alembic/versions/..._initial_schema.py`) đã được **autogenerate từ models thật**
và test trực tiếp trên Postgres 16 + pgvector (`upgrade head` → tạo đủ 11 bảng + enum types + cột
`vector(384)` → `downgrade base` → `upgrade head` lại sạch, không lỗi).

Khi sửa/thêm model (ví dụ thêm cột, thêm bảng mới cho Phase 2), tạo migration mới:

```bash
# sửa file trong app/models/... trước, sau đó:
docker compose exec backend alembic revision --autogenerate -m "mô tả thay đổi"
docker compose exec backend alembic upgrade head
```

Luôn mở file migration vừa sinh ra để kiểm tra lại (autogenerate không phải lúc nào cũng đoán đúng,
đặc biệt với cột kiểu đặc biệt như `pgvector.sqlalchemy.Vector` — cần đảm bảo `import pgvector.sqlalchemy`
có trong file, xem ví dụ ở migration đầu tiên).

Các lệnh Alembic hữu ích khác:

```bash
docker compose exec backend alembic current      # xem migration hiện tại của DB
docker compose exec backend alembic history       # xem lịch sử migration
docker compose exec backend alembic downgrade -1  # lùi lại 1 migration
```

## 8. Deployment Guide (tóm tắt)

- Dev: `docker compose up --build` như trên (có volume mount + `--reload`, tiện code trực tiếp).
- Production: bỏ `--reload`, bỏ volume mount source code, build image riêng, đặt `JWT_SECRET_KEY`
  mạnh, giới hạn `CORS_ORIGINS`, và dùng managed Postgres (RDS/Cloud SQL có hỗ trợ pgvector) + managed Redis.
  Service `migrate` vẫn chạy `alembic upgrade head` như một release step trước khi deploy `backend`/`worker` mới.
- CI/CD cơ bản: build + push image trên mỗi PR merge vào `main`, deploy qua GitHub Actions (khuyến khích
  ở guideline mục 13).

