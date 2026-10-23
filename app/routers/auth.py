from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm

from app.core.responses import error_responses
from app.dependencies import DbSession
from app.schemas.auth import RefreshTokenIn, TokenPair
from app.schemas.user import UserCreate, UserOut
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post(
    "/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Đăng ký tài khoản",
    responses=error_responses(409),
)
def register(data: UserCreate, db: DbSession):
    return auth_service.register(db, data)


@router.post(
    "/login",
    response_model=TokenPair,
    summary="Đăng nhập (trả về access_token + refresh_token)",
    responses=error_responses(401, 403),
)
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], db: DbSession):
    """Chuẩn OAuth2 Password Flow: gửi **form data** `username` + `password`.
    Tên field `username` là bắt buộc theo chuẩn OAuth2, giá trị là **email** của user."""
    return auth_service.login(db, form.username, form.password)


@router.post(
    "/refresh",
    response_model=TokenPair,
    summary="Đổi refresh token lấy cặp token mới (refresh token cũ hết dùng được)",
    responses=error_responses(401, 403),
)
def refresh(data: RefreshTokenIn, db: DbSession):
    return auth_service.refresh(db, data.refresh_token)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Đăng xuất: thu hồi refresh token (idempotent)",
)
def logout(data: RefreshTokenIn, db: DbSession):
    """Không cần access token: access token có thể đã hết hạn lúc user bấm đăng xuất.
    Access token hiện tại vẫn dùng được tới khi hết hạn (tối đa 15 phút), FE tự xóa nó."""
    auth_service.logout(db, data.refresh_token)
