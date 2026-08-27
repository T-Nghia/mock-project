# Smart Learning Resource Management System

Nền tảng quản lý tài liệu học tập thông minh dành cho sinh viên, giảng viên và quản trị viên. Hệ thống hỗ trợ tổ chức, tìm kiếm, chia sẻ tài liệu và hỏi đáp trên nội dung tài liệu bằng mô hình RAG.

## Tính năng chính

- Đăng ký, đăng nhập, làm mới token và khôi phục mật khẩu.
- Phân quyền theo vai trò `Student`, `Teacher` và `Admin`.
- Tải lên, xem trực tiếp, tải xuống và xóa tài liệu.
- Hỗ trợ PDF, DOC, DOCX, TXT, PPTX, JPG, JPEG và PNG; dung lượng tối đa mặc định 50 MB.
- Tổ chức tài liệu theo thư mục và thẻ.
- Tìm kiếm, lọc và truy xuất nội dung tài liệu bằng PostgreSQL/pgvector.
- Chat với tài liệu, lưu lịch sử hội thoại và gợi ý câu hỏi.
- Đánh dấu yêu thích, đánh giá và bình luận tài liệu.
- Dashboard thống kê và màn hình quản lý người dùng cho Admin.

## Công nghệ sử dụng

| Thành phần | Công nghệ |
| --- | --- |
| Frontend | Next.js 14, React 18, TypeScript, Tailwind CSS |
| Backend | FastAPI, SQLAlchemy 2, Pydantic 2 |
| Cơ sở dữ liệu | PostgreSQL 16, pgvector |
| Xác thực | JWT, bcrypt |
| AI/RAG | Gemini (tùy chọn), embedding và truy xuất bằng pgvector |
| Hạ tầng | Docker, Docker Compose, Redis |
| Migration | Alembic |

## Kiến trúc

Backend được tổ chức theo kiến trúc phân lớp:

```text
FastAPI Router → Service → Repository → PostgreSQL/pgvector
```

```text
.
├── backend/
│   ├── alembic/             # Database migrations
│   ├── app/
│   │   ├── api/routers/     # HTTP endpoints
│   │   ├── core/            # Cấu hình, database, bảo mật, phân quyền
│   │   ├── models/          # SQLAlchemy models
│   │   ├── repositories/    # Truy cập dữ liệu
│   │   ├── schemas/         # Pydantic request/response schemas
│   │   ├── services/        # Nghiệp vụ và AI/RAG
│   │   └── utils/           # Trích xuất, chia đoạn và xử lý văn bản
│   └── tests/
├── db/init.sql              # Khởi tạo extension pgvector
├── docs/                    # Tài liệu API, backend và database
├── frontend/                # Next.js App Router
├── .env.example
└── docker-compose.yml
```

## Chạy dự án bằng Docker

### Yêu cầu

- Git
- Docker Desktop hoặc Docker Engine có Docker Compose

### 1. Chuẩn bị biến môi trường

```bash
git clone <repository-url>
cd <repository-directory>
cp .env.example .env
```

Trên PowerShell, dùng lệnh sau thay cho `cp`:

```powershell
Copy-Item .env.example .env
```

Đổi `JWT_SECRET_KEY` trong `.env` trước khi dùng ở môi trường thật. `GEMINI_API_KEY` là tùy chọn; khi không có khóa, hệ thống dùng cơ chế tìm kiếm từ khóa và tóm tắt trích xuất cục bộ.

### 2. Khởi động

```bash
docker compose up --build
```

Service `migrate` sẽ tự động:

1. Chờ PostgreSQL sẵn sàng.
2. Chạy toàn bộ Alembic migration.
3. Tạo tài khoản Admin bootstrap nếu `ADMIN_EMAIL` và `ADMIN_PASSWORD` được cấu hình.
4. Cho phép backend khởi động sau khi hoàn tất.

Các địa chỉ sau sẽ khả dụng:

| Dịch vụ | Địa chỉ |
| --- | --- |
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| Swagger UI | http://localhost:8000/docs |
| Health check | http://localhost:8000/health |
| PostgreSQL | `localhost:5432` |
| Redis | `localhost:6379` |

Repo không chứa mật khẩu Admin mặc định. Để tạo Admin ban đầu, đặt đồng thời
`ADMIN_EMAIL` và `ADMIN_PASSWORD` trong `.env` trước khi chạy migrate. Nếu hai biến
đều trống, bước seed được bỏ qua. Người dùng có thể tự đăng ký tài khoản Student tại
`/register`; Admin có thể tạo Teacher và quản lý tài khoản tại `/admin/users`.

### 3. Dừng dự án

```bash
docker compose down
```

Để đồng thời xóa dữ liệu PostgreSQL và các tệp đã tải lên:

```bash
docker compose down -v
```

> Lệnh có `-v` xóa dữ liệu trong Docker volumes và không thể khôi phục nếu chưa sao lưu.

## Cấu hình

Các biến quan trọng trong `.env`:

| Biến | Mô tả |
| --- | --- |
| `DATABASE_URL` | Chuỗi kết nối PostgreSQL của backend |
| `REDIS_URL` | Chuỗi kết nối Redis |
| `JWT_SECRET_KEY` | Khóa dùng để ký JWT |
| `REFRESH_COOKIE_SECURE` | Bắt buộc `true` ở production để cookie chỉ đi qua HTTPS |
| `REFRESH_COOKIE_SAMESITE` | Dùng `none` khi frontend và backend ở khác site |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Thời hạn access token |
| `NEXT_PUBLIC_API_URL` | URL API được frontend sử dụng |
| `GEMINI_API_KEY` | Khóa Gemini để bật sinh câu trả lời và embedding bằng AI |
| `GEMINI_TEXT_MODEL` | Model Gemini dùng cho tác vụ văn bản |
| `GEMINI_EMBEDDING_MODEL` | Model tạo embedding |
| `GEMINI_EMBEDDING_DIM` | Số chiều embedding; mặc định `384` |
| `SMTP_*` | Cấu hình gửi email khôi phục mật khẩu |

Xem đầy đủ giá trị mẫu tại [`.env.example`](.env.example). Khi thay đổi số chiều embedding, cần bảo đảm cấu hình và kiểu vector trong database migration tương thích với nhau.

## Xử lý tài liệu và AI/RAG

Sau khi upload, backend dùng `BackgroundTasks` của FastAPI để trích xuất văn bản, chia đoạn, tạo embedding, tóm tắt và sinh câu hỏi gợi ý. Worker Celery trong `docker-compose.yml` hiện được tắt; Redis vẫn được khởi động để sẵn sàng cho luồng xử lý nền khi cần mở rộng.

Khi có `GEMINI_API_KEY`, hệ thống gọi Gemini cho các tác vụ AI đã cấu hình. Nếu không có khóa hợp lệ, ứng dụng vẫn chạy với cơ chế cục bộ để phục vụ phát triển và kiểm thử, nhưng chất lượng hiểu ngữ nghĩa sẽ thấp hơn model thật.

## Kiểm thử

Bộ test dùng `unittest` và có thể chạy ngay trong container backend:

```bash
docker compose exec backend python -m unittest discover -s tests -p "test_*.py"
```

Test tích hợp pgvector cần PostgreSQL đã migrate và có thể chạy riêng bằng:

```bash
docker compose exec backend python -m unittest tests.integration.test_retrieval_pgvector
```

Chạy kiểm tra frontend:

```bash
docker compose exec frontend npm run lint
```

## Database migration

Xem trạng thái và lịch sử migration:

```bash
docker compose exec backend alembic current
docker compose exec backend alembic history
```

Sau khi thay đổi SQLAlchemy model, tạo và áp dụng migration mới:

```bash
docker compose exec backend alembic revision --autogenerate -m "describe change"
docker compose exec backend alembic upgrade head
```

Luôn kiểm tra file migration được sinh tự động trước khi áp dụng, đặc biệt với kiểu dữ liệu `Vector` của pgvector.

## Tài liệu bổ sung

- [API documentation](docs/api-document.md)
- [OpenAPI specification](docs/openapi.json)
- [Backend design](docs/backend-design.md)
- [Database design](docs/database-design.md)
- [Hướng dẫn authentication](RUN_AUTH.md)
- [Hướng dẫn forgot/reset password](RUN_FORGOT_RESET_PASSWORD.md)

## Lưu ý khi triển khai production

- Thay toàn bộ secret và thông tin đăng nhập mặc định.
- Giới hạn `CORS_ORIGINS` theo domain thực tế.
- Không chạy Uvicorn với `--reload`.
- Không mount source code trực tiếp vào container.
- Dùng PostgreSQL có hỗ trợ pgvector và cấu hình lưu trữ bền vững cho uploads.
- Chạy `alembic upgrade head` như một bước phát hành trước khi khởi động phiên bản backend mới.
