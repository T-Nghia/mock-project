import unittest
import os

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ["DATABASE_URL"] = "sqlite://"

from app.core.database import Base, get_db
from app.core.security import hash_password
from app.main import app
from app.models.user import User, UserRole
from app.services import auth_service


class FakeRedis:
    def __init__(self):
        self.store = {}

    def setex(self, key, ttl, value):
        self.store[key] = value

    def get(self, key):
        return self.store.get(key)

    def delete(self, key):
        self.store.pop(key, None)

    def scan_iter(self, pattern):
        prefix = pattern.removesuffix("*")
        return [key for key in self.store if key.startswith(prefix)]


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


class AuthRBACTestCase(unittest.TestCase):
    def setUp(self):
        auth_service.redis_client = FakeRedis()
        self.client = TestClient(app)

        db = TestingSessionLocal()
        db.query(User).delete()
        db.commit()
        db.close()

    def create_user(
        self,
        email: str,
        role: UserRole,
        password: str = "Password@123",
        full_name: str = "Test User",
        is_active: bool = True,
    ) -> User:
        db = TestingSessionLocal()
        user = User(
            full_name=full_name,
            email=email,
            hashed_password=hash_password(password),
            role=role,
            is_active=is_active,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        db.expunge(user)
        db.close()
        return user

    def login(self, email: str, password: str = "Password@123") -> dict:
        response = self.client.post(
            "/auth/login",
            json={"email": email, "password": password},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    @staticmethod
    def auth_headers(token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def test_student_registration_login_refresh_and_permissions(self):
        register_response = self.client.post(
            "/auth/register",
            json={
                "full_name": "Student One",
                "email": "student@example.com",
                "password": "Password@123",
                "confirm_password": "Password@123",
            },
        )
        self.assertEqual(register_response.status_code, 201, register_response.text)
        self.assertEqual(register_response.json()["role"], "student")

        tokens = self.login("student@example.com")
        self.assertEqual(tokens["token_type"], "bearer")
        self.assertTrue(tokens["access_token"])
        self.assertNotIn("refresh_token", tokens)
        refresh_cookie = self.client.cookies.get("slrms_refresh_token")
        self.assertTrue(refresh_cookie)

        me_response = self.client.get(
            "/auth/me",
            headers=self.auth_headers(tokens["access_token"]),
        )
        self.assertEqual(me_response.status_code, 200)
        self.assertEqual(me_response.json()["email"], "student@example.com")

        refresh_response = self.client.post(
            "/auth/refresh",
        )
        self.assertEqual(refresh_response.status_code, 200, refresh_response.text)
        self.assertTrue(refresh_response.json()["access_token"])
        self.assertNotIn("refresh_token", refresh_response.json())
        self.assertNotEqual(
            self.client.cookies.get("slrms_refresh_token"),
            refresh_cookie,
        )

        missing_cookie_client = TestClient(app)
        missing_cookie_response = missing_cookie_client.post("/auth/refresh")
        self.assertEqual(missing_cookie_response.status_code, 401)

        permissions_response = self.client.get(
            "/auth/me/permissions",
            headers=self.auth_headers(tokens["access_token"]),
        )
        self.assertEqual(permissions_response.status_code, 200)
        permissions = permissions_response.json()["permissions"]
        self.assertIn("documents:read", permissions)
        self.assertNotIn("teachers:create", permissions)

        logout_response = self.client.post(
            "/auth/logout",
            headers=self.auth_headers(tokens["access_token"]),
        )
        self.assertEqual(logout_response.status_code, 204)
        self.assertIsNone(self.client.cookies.get("slrms_refresh_token"))

    def test_refresh_cookie_is_httponly_and_untrusted_origin_is_rejected(self):
        self.create_user("cookie@example.com", UserRole.STUDENT)
        login_response = self.client.post(
            "/auth/login",
            json={"email": "cookie@example.com", "password": "Password@123"},
        )

        cookie_header = login_response.headers["set-cookie"].lower()
        self.assertIn("httponly", cookie_header)
        self.assertIn("samesite=lax", cookie_header)
        self.assertIn("path=/auth", cookie_header)
        self.assertNotIn("refresh_token", login_response.json())

        rejected = self.client.post(
            "/auth/refresh",
            headers={"Origin": "https://attacker.example"},
        )
        self.assertEqual(rejected.status_code, 403)

    def test_student_and_teacher_cannot_create_teacher(self):
        self.create_user("student@example.com", UserRole.STUDENT)
        self.create_user("teacher@example.com", UserRole.TEACHER)

        student_tokens = self.login("student@example.com")
        teacher_tokens = self.login("teacher@example.com")

        payload = {
            "full_name": "New Teacher",
            "email": "new.teacher@example.com",
            "password": "Password@123",
        }

        student_response = self.client.post(
            "/auth/admin/teachers",
            json=payload,
            headers=self.auth_headers(student_tokens["access_token"]),
        )
        self.assertEqual(student_response.status_code, 403)

        teacher_response = self.client.post(
            "/auth/admin/teachers",
            json={**payload, "email": "another.teacher@example.com"},
            headers=self.auth_headers(teacher_tokens["access_token"]),
        )
        self.assertEqual(teacher_response.status_code, 403)

    def test_admin_can_manage_teachers_and_users(self):
        self.create_user("admin@example.com", UserRole.ADMIN, full_name="Admin User")
        student = self.create_user(
            "student@example.com",
            UserRole.STUDENT,
            full_name="Student User",
        )
        admin_tokens = self.login("admin@example.com")

        create_teacher_response = self.client.post(
            "/auth/admin/teachers",
            json={
                "full_name": "Teacher User",
                "email": "teacher@example.com",
                "password": "Password@123",
            },
            headers=self.auth_headers(admin_tokens["access_token"]),
        )
        self.assertEqual(create_teacher_response.status_code, 201, create_teacher_response.text)
        self.assertEqual(create_teacher_response.json()["role"], "teacher")

        list_response = self.client.get(
            "/auth/admin/users",
            headers=self.auth_headers(admin_tokens["access_token"]),
        )
        self.assertEqual(list_response.status_code, 200)
        self.assertGreaterEqual(
            {user["email"] for user in list_response.json()},
            {"admin@example.com", "student@example.com", "teacher@example.com"},
        )

        role_response = self.client.patch(
            f"/auth/admin/users/{student.id}/role",
            json={"role": "teacher"},
            headers=self.auth_headers(admin_tokens["access_token"]),
        )
        self.assertEqual(role_response.status_code, 200, role_response.text)
        self.assertEqual(role_response.json()["role"], "teacher")

        teacher_id = create_teacher_response.json()["id"]
        status_response = self.client.patch(
            f"/auth/admin/users/{teacher_id}/status",
            json={"is_active": False},
            headers=self.auth_headers(admin_tokens["access_token"]),
        )
        self.assertEqual(status_response.status_code, 200, status_response.text)
        self.assertIs(status_response.json()["is_active"], False)

        disabled_login_response = self.client.post(
            "/auth/login",
            json={"email": "teacher@example.com", "password": "Password@123"},
        )
        self.assertEqual(disabled_login_response.status_code, 403)

    def test_admin_cannot_demote_or_disable_self(self):
        admin = self.create_user("admin@example.com", UserRole.ADMIN, full_name="Admin User")
        admin_tokens = self.login("admin@example.com")

        demote_response = self.client.patch(
            f"/auth/admin/users/{admin.id}/role",
            json={"role": "student"},
            headers=self.auth_headers(admin_tokens["access_token"]),
        )
        self.assertEqual(demote_response.status_code, 400)

        disable_response = self.client.patch(
            f"/auth/admin/users/{admin.id}/status",
            json={"is_active": False},
            headers=self.auth_headers(admin_tokens["access_token"]),
        )
        self.assertEqual(disable_response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
