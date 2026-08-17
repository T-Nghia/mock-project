import uuid

from datetime import datetime, timedelta, timezone
from fastapi import BackgroundTasks, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.permissions import get_role_permissions
from app.core.redis_client import redis_client
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    generate_password_reset_token,
    hash_password,
    hash_password_reset_token,
    verify_password,
)
from app.models.user import User, UserRole
from app.repositories.password_reset_repo import PasswordResetRepository
from app.repositories.user_repo import UserRepository
from app.schemas.auth import (
    ForgotPasswordRequest,
    ResetPasswordRequest,
    TeacherCreate,
    TokenResponse,
    UserLogin,
    UserRegister,
    UserRoleUpdate,
    UserStatusUpdate,
)
from app.utils.email import send_email


class AuthService:

    _DUMMY_HASH = hash_password("this-is-not-a-real-password") # Tính 1 lần lúc import module

    def __init__(self, db: Session):
        self.repo = UserRepository(db)
        self.reset_repo = PasswordResetRepository(db)

    def register(self, data: UserRegister) -> User:
        if hasattr(data, "confirm_password") and data.password != data.confirm_password:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Mat khau xac nhan khong khop")

        if self.repo.get_by_email(data.email):
            raise HTTPException(status.HTTP_409_CONFLICT, "Email da duoc su dung")

        return self.repo.create(
            data.full_name,
            data.email,
            hash_password(data.password),
            role=UserRole.STUDENT,
        )

    def create_teacher(self, data: TeacherCreate) -> User:
        if self.repo.get_by_email(data.email):
            raise HTTPException(status.HTTP_409_CONFLICT, "Email da duoc su dung")

        return self.repo.create(
            data.full_name,
            data.email,
            hash_password(data.password),
            role=UserRole.TEACHER,
        )

    def list_users(self) -> list[User]:
        return self.repo.list_all()

    def update_user_role(
        self,
        user_id: uuid.UUID,
        data: UserRoleUpdate,
        current_user_id: uuid.UUID,
    ) -> User:
        user = self.repo.get_by_id(user_id)
        if not user:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Nguoi dung khong ton tai")

        if user.id == current_user_id and data.role != UserRole.ADMIN:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Admin khong the ha quyen chinh minh")

        return self.repo.update_role(user, data.role)

    def update_user_status(
        self,
        user_id: uuid.UUID,
        data: UserStatusUpdate,
        current_user_id: uuid.UUID,
    ) -> User:
        user = self.repo.get_by_id(user_id)
        if not user:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Nguoi dung khong ton tai")

        if user.id == current_user_id and not data.is_active:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Admin khong the vo hieu hoa chinh minh")

        return self.repo.update_active_status(user, data.is_active)

    def get_permissions(self, user: User) -> dict[str, str | list[str]]:
        role = getattr(user.role, "value", user.role)
        permissions = sorted(permission.value for permission in get_role_permissions(user.role))
        return {"role": role, "permissions": permissions}

    def _issue_tokens(self, user: User) -> TokenResponse:
        access = create_access_token(str(user.id), user.role.value)
        refresh, jti = create_refresh_token(str(user.id), user.role.value)
        redis_client.setex(
            f"refresh:{user.id}:{jti}",
            settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
            "valid",
        ) # Hỗ trợ 1 phiên đăng nhập/user
        return TokenResponse(access_token=access, refresh_token=refresh)

    def login(self, data: UserLogin) -> TokenResponse:
        user = self.repo.get_by_email(data.email)
        password_ok = verify_password(data.password, user.hashed_password if user else self._DUMMY_HASH) # Tránh timing attack
        if not user or not password_ok:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email hoac mat khau khong dung")

        if not user.is_active:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Tai khoan da bi vo hieu hoa")

        return self._issue_tokens(user)

    def refresh(self, refresh_token: str) -> TokenResponse:
        payload = decode_access_token(refresh_token)
        if payload is None or payload.get("type") != "refresh":
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token khong hop le hoac da het han")

        key = f"refresh:{payload['sub']}:{payload['jti']}"
        if not redis_client.get(key):
            raise HTTPException(401, "Refresh token da bi thu hoi")
        redis_client.delete(key)

        user = self.repo.get_by_id(uuid.UUID(payload["sub"]))
        if not user or not user.is_active:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token khong hop le")

        return self._issue_tokens(user)

    def logout(self, user_id: uuid.UUID, jti: str | None = None):
        if jti:
            redis_client.delete(f"refresh:{user_id}:{jti}")
        else:
            for key in redis_client.scan_iter(f"refresh:{user_id}:*"):
                redis_client.delete(key)

    def forgot_password(self, data: ForgotPasswordRequest, background_tasks: BackgroundTasks) -> None:
        user = self.repo.get_by_email(data.email)
        if user and user.is_active:
            self.reset_repo.invalidate_all_for_user(user.id)

            raw_token = generate_password_reset_token()
            token_hash = hash_password_reset_token(raw_token)
            expires_at = datetime.now(timezone.utc) + timedelta(
                minutes=settings.PASSWORD_RESET_EXPIRE_MINUTES
            )
            self.reset_repo.create(user.id, token_hash, expires_at)

            reset_link = f"{settings.FRONTEND_URL}/reset-password?token={raw_token}"
            background_tasks.add_task(
                send_email,
                to=user.email,
                subject="Dat lai mat khau - Smart LRMS",
                body=f"Nhan vao link sau de dat lai mat khau (het han sau {settings.PASSWORD_RESET_EXPIRE_MINUTES} phut):\n{reset_link}",
            )

    def reset_password(self, data: ResetPasswordRequest) -> None:
        if data.new_password != data.confirm_new_password:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Mat khau xac nhan khong khop")

        token_hash = hash_password_reset_token(data.token)
        reset_row = self.reset_repo.get_valid_by_hash(token_hash)
        if reset_row is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Token khong hop le hoac da het han")

        user = self.repo.get_by_id(reset_row.user_id)
        if not user or not user.is_active:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Token khong hop le")

        user.hashed_password = hash_password(data.new_password)
        self.repo.db.commit()
        self.reset_repo.mark_used(reset_row)

        self.logout(user.id) # Thu hồi toàn bộ refresh token cũ
