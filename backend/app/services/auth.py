from fastapi import HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User, UserRole
from app.repositories.user import create_user, get_user_by_email
from app.schemas.auth import LoginRequest, RegisterRequest


INVALID_LOGIN_MESSAGE = "Email hoặc mật khẩu không chính xác"


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def register_user(db: Session, request: RegisterRequest) -> User:
    if request.password != request.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mật khẩu xác nhận không khớp",
        )

    full_name = request.full_name.strip()
    if not full_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Họ tên không được để trống",
        )

    email = _normalize_email(request.email)
    if get_user_by_email(db, email) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email đã được sử dụng",
        )

    user = User(
        full_name=full_name,
        email=email,
        hashed_password=hash_password(request.password),
        role=UserRole.STUDENT,
    )

    try:
        user = create_user(db, user)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Không thể đăng ký tài khoản. Vui lòng thử lại.",
        ) from exc

    return user


def login_user(db: Session, request: LoginRequest) -> tuple[User, str]:
    user = get_user_by_email(db, _normalize_email(request.email))
    if user is None or not verify_password(request.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=INVALID_LOGIN_MESSAGE,
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tài khoản đã bị vô hiệu hóa",
        )

    token = create_access_token(subject=str(user.id), role=user.role.value)
    return user, token
