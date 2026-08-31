from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Cookie, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.config import settings
from app.core.permissions import Permission
from app.core.rate_limit import auth_rate_limit
from app.core.security import get_current_user, require_permission, require_role
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TeacherCreate,
    TokenResponse,
    UserPermissionsResponse,
    UserResponse,
    UserRoleUpdate,
    UserStatusUpdate,
)
from app.services.auth_service import AuthService


router = APIRouter(prefix="/auth", tags=["Authentication"])


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        value=refresh_token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        httponly=True,
        secure=settings.REFRESH_COOKIE_SECURE,
        samesite=settings.REFRESH_COOKIE_SAMESITE.lower(),
        path=settings.REFRESH_COOKIE_PATH,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        httponly=True,
        secure=settings.REFRESH_COOKIE_SECURE,
        samesite=settings.REFRESH_COOKIE_SAMESITE.lower(),
        path=settings.REFRESH_COOKIE_PATH,
    )


def _validate_cookie_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin and origin not in settings.CORS_ORIGINS:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Origin khong duoc phep")


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(auth_rate_limit("register"))])
def register(data: RegisterRequest, db: Session = Depends(get_db)):
    return AuthService(db).register(data)


@router.post("/login", response_model=TokenResponse,
             dependencies=[Depends(auth_rate_limit("login"))])
def login(data: LoginRequest, response: Response, db: Session = Depends(get_db)):
    tokens = AuthService(db).login(data)
    _set_refresh_cookie(response, tokens.refresh_token)
    return TokenResponse(access_token=tokens.access_token)


@router.post("/login/swagger", response_model=TokenResponse, include_in_schema=False,
             dependencies=[Depends(auth_rate_limit("login"))])
def login_swagger(
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(), 
    db: Session = Depends(get_db)
):
    # Map dữ liệu Form Data từ Swagger sang LoginRequest schema
    login_data = LoginRequest(email=form_data.username, password=form_data.password)
    tokens = AuthService(db).login(login_data)
    _set_refresh_cookie(response, tokens.refresh_token)
    return TokenResponse(access_token=tokens.access_token)


@router.post("/refresh", response_model=TokenResponse,
             dependencies=[Depends(auth_rate_limit("refresh"))])
def refresh(
    request: Request,
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=settings.REFRESH_COOKIE_NAME),
    db: Session = Depends(get_db),
):
    _validate_cookie_origin(request)
    if not refresh_token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh cookie khong ton tai")
    tokens = AuthService(db).refresh(refresh_token)
    _set_refresh_cookie(response, tokens.refresh_token)
    return TokenResponse(access_token=tokens.access_token)


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED,
             dependencies=[Depends(auth_rate_limit("forgot-password"))])
def forgot_password(
    data: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    AuthService(db).forgot_password(data, background_tasks)
    return {"Message": "Neu email ton tai trong he thong, huong dan dat lai mat khau da duoc gui."}


@router.post("/reset-password", dependencies=[Depends(auth_rate_limit("reset-password"))])
def reset_password(data: ResetPasswordRequest, db: Session = Depends(get_db)):
    AuthService(db).reset_password(data)
    return {"Message": "Dat lai mat khau thanh cong."}


@router.get("/me", response_model=UserResponse)
def get_me(current_user=Depends(get_current_user)):
    return current_user


@router.get("/me/permissions", response_model=UserPermissionsResponse)
def get_my_permissions(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return AuthService(db).get_permissions(current_user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _validate_cookie_origin(request)
    AuthService(db).logout(current_user.id)
    _clear_refresh_cookie(response)


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
