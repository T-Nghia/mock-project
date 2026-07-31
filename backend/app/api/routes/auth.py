from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user, require_role
from app.schemas.auth import UserRegister, UserLogin, TokenResponse, RefreshRequest, TeacherCreate, UserResponse
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Auth"])

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(data: UserRegister, db: Session = Depends(get_db)):
    return AuthService(db).register(data)

@router.post("/login", response_model=TokenResponse)
def login(data: UserLogin, db: Session = Depends(get_db)):
    return AuthService(db).login(data)

@router.post("/refresh", response_model=TokenResponse)
def refresh(data: RefreshRequest, db: Session = Depends(get_db)):
    return AuthService(db).refresh(data.refresh_token)

@router.get("/me", response_model=UserResponse)
def get_me(current_user=Depends(get_current_user)):
    return current_user

@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    AuthService(db).logout(current_user.id)

@router.post("/admin/teachers", response_model=UserResponse, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_role("admin"))])
def create_teacher(data: TeacherCreate, db: Session = Depends(get_db)):
    return AuthService(db).create_teacher(data)