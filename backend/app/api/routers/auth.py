from uuid import UUID

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permissions import Permission
from app.core.security import get_current_user, require_permission, require_role
from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TeacherCreate,
    TokenResponse,
    UserPermissionsResponse,
    UserResponse,
    UserRoleUpdate,
    UserStatusUpdate,
)
from app.services.auth_service import AuthService


router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(data: RegisterRequest, db: Session = Depends(get_db)):
    return AuthService(db).register(data)


@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    return AuthService(db).login(data)


@router.post("/login/swagger", response_model=TokenResponse, include_in_schema=False)
def login_swagger(
    form_data: OAuth2PasswordRequestForm = Depends(), 
    db: Session = Depends(get_db)
):
    # Map dữ liệu Form Data từ Swagger sang LoginRequest schema
    login_data = LoginRequest(email=form_data.username, password=form_data.password)
    return AuthService(db).login(login_data)


@router.post("/refresh", response_model=TokenResponse)
def refresh(data: RefreshRequest, db: Session = Depends(get_db)):
    return AuthService(db).refresh(data.refresh_token)


@router.get("/me", response_model=UserResponse)
def get_me(current_user=Depends(get_current_user)):
    return current_user


@router.get("/me/permissions", response_model=UserPermissionsResponse)
def get_my_permissions(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return AuthService(db).get_permissions(current_user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    AuthService(db).logout(current_user.id)


@router.post(
    "/admin/teachers",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(Permission.CREATE_TEACHER))],
)
def create_teacher(data: TeacherCreate, db: Session = Depends(get_db)):
    return AuthService(db).create_teacher(data)


@router.get(
    "/admin/users",
    response_model=list[UserResponse],
    dependencies=[Depends(require_permission(Permission.VIEW_USERS))],
)
def list_users(db: Session = Depends(get_db)):
    return AuthService(db).list_users()


@router.patch(
    "/admin/users/{user_id}/role",
    response_model=UserResponse,
    dependencies=[Depends(require_permission(Permission.UPDATE_USER_ROLE))],
)
def update_user_role(
    user_id: UUID,
    data: UserRoleUpdate,
    current_user=Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    return AuthService(db).update_user_role(user_id, data, current_user.id)


@router.patch(
    "/admin/users/{user_id}/status",
    response_model=UserResponse,
    dependencies=[Depends(require_permission(Permission.UPDATE_USER_STATUS))],
)
def update_user_status(
    user_id: UUID,
    data: UserStatusUpdate,
    current_user=Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    return AuthService(db).update_user_status(user_id, data, current_user.id)
