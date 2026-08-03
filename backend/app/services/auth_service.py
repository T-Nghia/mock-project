import uuid
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.redis_client import redis_client
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.models.user import UserRole
from app.repositories.user_repo import UserRepository
from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TeacherCreate,
    TokenResponse,
    UserLogin,      # Alias tương thích
    UserRegister,   # Alias tương thích
)

class AuthService:
    def __init__(self, db: Session):
        self.repo = UserRepository(db)

    def register(self, data: UserRegister):
        if hasattr(data, 'confirm_password') and data.password != data.confirm_password:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Mật khẩu xác nhận không khớp")
        
        if self.repo.get_by_email(data.email):
            raise HTTPException(status.HTTP_409_CONFLICT, "Email đã được sử dụng")
        return self.repo.create(data.full_name, data.email, hash_password(data.password), role=UserRole.STUDENT)

    def create_teacher(self, data: TeacherCreate):
        if self.repo.get_by_email(data.email):
            raise HTTPException(status.HTTP_409_CONFLICT, "Email đã được sử dụng")
        return self.repo.create(data.full_name, data.email, hash_password(data.password), role=UserRole.TEACHER)

    def _issue_tokens(self, user) -> TokenResponse:
        access = create_access_token(str(user.id), user.role.value)
        refresh, jti = create_refresh_token(str(user.id), user.role.value)
        redis_client.setex(f"refresh:{user.id}", settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400, jti)
        return TokenResponse(access_token=access, refresh_token=refresh)

    def login(self, data: UserLogin) -> TokenResponse:
        user = self.repo.get_by_email(data.email)
        if not user or not verify_password(data.password, user.hashed_password):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email hoặc mật khẩu không đúng")

        if not user.is_active:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Tài khoản đã bị vô hiệu hóa")
        
        return self._issue_tokens(user)

    def refresh(self, refresh_token: str) -> TokenResponse:
        payload = decode_access_token(refresh_token)
        if payload is None or payload.get("type") != "refresh":
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token không hợp lệ hoặc đã hết hạn")

        stored_jti = redis_client.get(f"refresh:{payload['sub']}")
        if not stored_jti or stored_jti != payload.get("jti"):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token đã bị thu hồi")

        user = self.repo.get_by_id(uuid.UUID(payload["sub"]))
        if not user or not user.is_active:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token không hợp lệ")
        return self._issue_tokens(user)

    def logout(self, user_id: uuid.UUID):
        redis_client.delete(f"refresh:{user_id}")