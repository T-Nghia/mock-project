# Run Auth Backend

Huong dan nay dung cho phan backend auth hien tai: dang ky, dang nhap,
PostgreSQL, Redis va Alembic migration.

## 1. Chuan bi

Mo PowerShell tai thu muc goc cua project vua clone/tai ve, tuc la thu muc co
file `docker-compose.yml`, `README.md`, `backend/`, `db/`.

Vi du neu project nam trong thu muc `my-project`:

```powershell
cd path\to\my-project
```

Neu ban dang mo terminal ngay trong thu muc project roi thi khong can chay lenh
`cd` nua.

Tao file `.env` neu chua co:

```powershell
Copy-Item .env.example .env
```

Neu dang co container khac chiem port `5432`, hay dung no truoc:



## 2. Chay backend auth

Chi chay service `backend`:

```powershell
docker compose up --build backend
```

Lenh nay se tu keo theo cac service can thiet:

```text
db
redis
migrate
backend
```

Khi thay log sau la backend da chay:

```text
Uvicorn running on http://0.0.0.0:8000
Application startup complete.
```

Mo Swagger UI:

```text
http://localhost:8000/docs
```

## 3. Test API

Health check:

```text
GET /health
```

Dang ky:

```text
POST /auth/register
```

Body mau:

```json
{
  "full_name": "Nguyen Van An",
  "email": "an@example.com",
  "password": "Student@123",
  "confirm_password": "Student@123"
}
```

Ket qua dung:

```text
201 Created
```

Dang nhap:

```text
POST /auth/login
```

Body mau:

```json
{
  "email": "an@example.com",
  "password": "Student@123"
}
```

Ket qua dung:

```text
200 OK
```

Response co `access_token` va `token_type` la `bearer`.

## 4. Test loi nen co

Dang ky trung email:

```text
409 Conflict
```

Sai mat khau khi dang nhap:

```text
401 Unauthorized
```

Email sai dinh dang:

```text
422 Unprocessable Entity
```

## 5. Dung service

Neu dang chay foreground, bam:

```text
Ctrl + C
```

Hoac dung Docker Compose:

```powershell
docker compose down
```

Neu muon xoa luon database local va chay lai tu dau:

```powershell
docker compose down -v
```

## 6. Ghi chu cho nguoi lam tiep Auth

Phan hien tai da co:

```text
POST /auth/register
POST /auth/login
```

Bo cuc file:

```text
backend/app/api/routes/auth.py      # endpoint Register/Login
backend/app/schemas/auth.py         # request/response schema
backend/app/services/auth.py        # business logic
backend/app/repositories/user.py    # truy van/ghi bang users
backend/app/core/security.py        # hash password, verify password, JWT helper
```

Neu lam tiep JWT cho cac request sau khi dang nhap, nen them dependency rieng,
vi du:

```text
backend/app/api/deps.py
```

Trong do co the dat cac ham:

```text
get_current_user()
require_role()
```

Neu lam tiep Role Permission, nen dung `require_role()` de bao ve endpoint theo
role `admin`, `teacher`, `student`, thay vi chi an/hien nut o frontend.
