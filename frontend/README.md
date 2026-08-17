# SLRMS Frontend

Next.js 14 (App Router) + TypeScript + Tailwind CSS + shadcn/ui-style components.

## Cấu trúc chính
- `app/login`, `app/register` — xác thực (đăng ký luôn tạo tài khoản STUDENT).
- `app/(app)/*` — khu vực đã đăng nhập, bảo vệ bởi `AppShell` (redirect nếu chưa login / sai role).
  - `dashboard` — thống kê tổng quan theo role (admin thấy thêm users_by_role).
  - `documents/upload` — chỉ teacher/admin.
  - `documents/[id]` — xem metadata, tải xuống, xem tóm tắt AI.
  - `folders` — chỉ teacher/admin: cây thư mục, CRUD, chuyển tài liệu giữa thư mục.
  - `search` — tìm kiếm tài liệu (mọi role).
  - `admin/users` — chỉ admin: đổi vai trò, khoá/mở khoá, tạo giáo viên.
- `lib/api.ts` — API client dùng chung, tự refresh access token khi gặp 401.
- `lib/auth-context.tsx` — quản lý phiên đăng nhập (React Context).
- `components/ui/*` — bộ component kiểu shadcn/ui (tự viết, không phụ thuộc Radix để nhẹ và dễ build).

## Chạy thử
```bash
npm install
cp .env.local.example .env.local   # chỉnh NEXT_PUBLIC_API_URL nếu cần
npm run dev
```

## Build production (đã test build thành công)
```bash
npm run build && npm start
```

## Docker
Bật lại service `frontend` trong `docker-compose.yml` ở thư mục gốc (hiện đang bị comment).

## Ghi chú
- Backend trả JWT qua `/auth/login` (không kèm user) → sau khi login, client tự gọi `/auth/me`.
- Đăng ký công khai (`/auth/register`) luôn tạo role STUDENT; tài khoản TEACHER do ADMIN tạo qua trang Quản lý người dùng.
- Toàn bộ tuỳ chỉnh Tailwind theme (màu, radius...) nằm ở `app/globals.css` (CSS variables) và `tailwind.config.ts`.
