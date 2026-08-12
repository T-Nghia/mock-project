# Run Forgot / Reset Password

Hướng dẫn này dùng cho tính năng Quên mật khẩu (Forgot Password) và Đặt lại
mật khẩu (Reset Password), xây trên nền Auth đã có sẵn (đăng ký, đăng nhập,
PostgreSQL, Redis, Alembic).

## 1. Chuẩn bị

Giả sử backend Auth (đăng ký/đăng nhập) đã chạy được theo hướng dẫn
`Run Auth Backend`. Kiểm tra file `.env` đã có đủ các biến sau (thêm vào nếu
chưa có):

```dotenv
PASSWORD_RESET_EXPIRE_MINUTES=15
FRONTEND_URL=http://localhost:3000

SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM_EMAIL=noreply@slrms.local
```

Để trống `SMTP_HOST` là bình thường - email sẽ được in ra log thay vì gửi
thật, dùng để test.

## 2. Áp dụng migration mới

Bảng `password_reset_tokens` cần được tạo trước khi test. Vì service
`migrate` chỉ chạy 1 lần lúc container mới, chạy lại bằng tay:

```powershell
docker compose run --rm migrate
```

## 3. Cập nhật backend để nhận biến môi trường mới

File `.env` không tự được container đọc lại chỉ bằng `--reload`. Recreate
container:

```powershell
docker compose up -d --force-recreate backend
```

## 4. Test luồng Quên mật khẩu

```text
POST /auth/forgot-password
```

Body mẫu:

```json
{
  "email": "an@example.com"
}
```

Kết quả đúng:

```text
202 Accepted
```

Lưu ý: response trả về giống hệt nhau dù email có tồn tại trong hệ thống hay
không (cố tình, tránh lộ email đã đăng ký). Nếu gửi với email KHÔNG tồn tại,
vẫn nhận `202 Accepted` nhưng sẽ KHÔNG thấy dòng `[DEV EMAIL]` nào in ra log ở
bước tiếp theo - đây là hành vi đúng, không phải lỗi.

## 5. Lấy token từ log (vì localhost:3000 chưa hoạt động)

Trang `/reset-password` bên frontend chưa được dựng xong, nên KHÔNG bấm vào
link trong email. Thay vào đó, xem log backend:

```powershell
docker compose logs -f backend
```

Tìm đoạn giống như sau:

```text
[DEV EMAIL] To: an@example.com
Subject: Dat lai mat khau - Smart LRMS
Nhan vao link sau de dat lai mat khau (het han sau 15 phut):
http://localhost:3000/reset-password?token=41CEWOkzoQLz2rZpADaNGDwgBqQWs2suxpqER0WGCt8
```

Copy phần giá trị sau `token=` (không copy cả URL) - đây là giá trị sẽ dán
vào Swagger ở bước tiếp theo.

## 6. Test luồng Đặt lại mật khẩu

```text
POST /auth/reset-password
```

Body mẫu (thay `token` bằng giá trị vừa copy ở bước 5):

```json
{
  "token": "41CEWOkzoQLz2rZpADaNGDwgBqQWs2suxpqER0WGCt8",
  "new_password": "Student@456",
  "confirm_new_password": "Student@456"
}
```

Kết quả đúng:

```text
200 OK
```

Response:

```json
{ "message": "Dat lai mat khau thanh cong." }
```

Xác nhận lại bằng cách đăng nhập với mật khẩu MỚI qua `POST /auth/login` -
mật khẩu cũ sẽ không còn dùng được.

## 7. Test lỗi nên có

Dùng lại đúng token vừa dùng để reset thành công (gọi lần 2):

```text
400 Bad Request
```

Đợi qua thời gian `PASSWORD_RESET_EXPIRE_MINUTES` (mặc định 15 phút) rồi mới
dùng token:

```text
400 Bad Request
```

`new_password` khác `confirm_new_password`:

```text
422	Error: Unprocessable Entity
```

Token sai/không tồn tại (gõ bừa):

```text
400 Bad Request
```

Sau khi đặt lại mật khẩu thành công, các access token/refresh token cũ (nếu
đã đăng nhập trước đó trên thiết bị khác) sẽ không còn dùng được - toàn bộ
phiên đăng nhập cũ bị thu hồi (logout khỏi mọi thiết bị).

## 8. Dừng service

Nếu đang chạy foreground, bấm:

```text
Ctrl + C
```

Hoặc dừng Docker Compose:

```powershell
docker compose down
```

Nếu muốn xoá luôn database local và chạy lại từ đầu:

```powershell
docker compose down -v
```

## 9. Ghi chú

Phần hiện tại đã có:

```text
POST /auth/forgot-password
POST /auth/reset-password
```

Bố cục file:

```text
backend/app/models/password_reset_token.py       # bảng lưu token đã hash (sha256), không lưu token gốc
backend/app/repositories/password_reset_repo.py  # create / get_valid_by_hash / mark_used / invalidate_all_for_user
backend/app/services/auth_service.py             # forgot_password(), reset_password()
backend/app/api/routers/auth_router.py           # POST /auth/forgot-password, POST /auth/reset-password
backend/app/utils/email.py                       # send_email() - in ra log nếu chưa cấu hình SMTP thật
backend/app/core/security.py                     # generate_password_reset_token(), hash_password_reset_token()
```

Nếu làm tiếp phần frontend: cần dựng trang `/reset-password` nhận query
param `token` từ URL, hiển thị form nhập mật khẩu mới + xác nhận, gọi
`POST /auth/reset-password`.

Nếu muốn gửi email thật (không chỉ in log): điền `SMTP_HOST`, `SMTP_PORT`,
`SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL` vào `.env` rồi recreate
container `backend`.