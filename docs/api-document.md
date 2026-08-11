# API Document — Sprint 1

## 1. Swagger / OpenAPI

FastAPI tự sinh tài liệu API trực tiếp từ code (router + Pydantic schema), nên
đây luôn là bản mô tả **chính xác nhất** với API thật — không cần viết tay lại
từng field.

Khi chạy backend (`docker compose up` hoặc `uvicorn app.main:app`), truy cập:

| Giao diện | URL | Dùng để |
|---|---|---|
| Swagger UI | `http://localhost:8000/docs` | Xem + thử trực tiếp từng endpoint trên trình duyệt |
| ReDoc | `http://localhost:8000/redoc` | Xem tài liệu dạng đọc (không gọi thử được) |
| OpenAPI JSON thô | `http://localhost:8000/openapi.json` | Import vào Postman/Insomnia hoặc sinh client code |

Cách thử nhanh với Swagger UI cho các API cần đăng nhập:
1. Gọi `POST /auth/register` hoặc dùng tài khoản có sẵn từ `python -m app.seed`.
2. Gọi `POST /auth/login` lấy `access_token`.
3. Bấm nút **Authorize** ở Swagger UI, nhập `Bearer <access_token>`.
4. Gọi thử các endpoint còn lại.

## 2. Snapshot OpenAPI cuối Sprint 1

File [`openapi.json`](./openapi.json) trong cùng thư mục là bản export tĩnh
của `/openapi.json` tại thời điểm cuối Sprint 1 — dùng để đối chiếu/chấm điểm
mà không cần dựng backend lên chạy. **Đây chỉ là snapshot tham khảo** — nguồn
sự thật (source of truth) vẫn luôn là `/docs` khi chạy code thật, vì snapshot
sẽ lỗi thời ngay khi code đổi.

Để tự tạo lại snapshot mới sau khi sửa code (chạy trong thư mục `backend/`):

```bash
python3 -c "
import json
from fastapi.testclient import TestClient
from app.main import app
schema = TestClient(app).get('/openapi.json').json()
json.dump(schema, open('../docs/openapi.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
"
```

## 3. Tóm tắt endpoint

Xem bảng đầy đủ theo từng module (Auth, Document, Folder, Search, Dashboard)
tại [`backend-design.md`](./backend-design.md) mục **2. API Design** — không
lặp lại ở đây để tránh 2 nơi có thể lệch nhau.

## 4. Ghi chú đã biết (cuối Sprint 1)

- Response lỗi hiện dùng nguyên format mặc định của FastAPI
  (`{"detail": "..."}`) cho mọi module — chưa có mã lỗi nghiệp vụ riêng
  (error code), có thể cần bổ sung khi Frontend Sprint 2 cần phân biệt loại
  lỗi để hiển thị thông báo khác nhau.
