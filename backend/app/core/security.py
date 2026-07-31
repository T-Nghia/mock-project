import uuid

from datetime import datetime, timedelta, timezone

from jose import jwt, JWTError
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl = "api/v1/auth/login")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(subject: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {"sub": subject, "role": role, "exp": expire}
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
    except JWTError:
        return None

def get_current_user(token:str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    from app.repositories.user_repository import UserRepository

    payload = decode_access_token(token)
    if payload is None or payload.get('Type') != 'access':
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token không hợp lệ hoặc đã hết hạn",
                            headers = {"WWW-Authenticate": "Bearer"})

    try:
        user_id = uuid.UUID(payload["sub"])
    except:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token không hợp lệ")

    user = UserRepository(db).get_by_id(user_id)
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token không hợp lệ hoặc đã hết hạn")
    return user

def require_role(*roles: str):
    def checker(current_user=Depends(get_current_user)):
        if current_user.role.value not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Không có quyền truy cập")
        return current_user
    return checker