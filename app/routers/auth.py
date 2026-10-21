from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.exc import IntegrityError

from app import crud
from app.core import messages
from app.core.exceptions import ConflictException
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
    if crud.user.get_by_username(db, data.username):
        raise ConflictException(messages.USERNAME_TAKEN)
    if crud.user.get_by_email(db, data.email):
        raise ConflictException(messages.EMAIL_TAKEN)
    try:
        return crud.user.create(db, data)
    except IntegrityError:
        # 2 request đăng ký cùng username gần như đồng thời: cả 2 đều qua bước kiểm tra
        # ở trên, nhưng UNIQUE constraint trong DB vẫn chặn được request thứ 2.
        db.rollback()
        raise ConflictException(messages.USERNAME_OR_EMAIL_TAKEN) from None


@router.post(
    "/login",
    response_model=TokenPair,
    summary="Đăng nhập (trả về access_token + refresh_token)",
    responses=error_responses(401, 403),
)
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], db: DbSession):
    """Chuẩn OAuth2 Password Flow: gửi **form data** `username` + `password`
    (field `username` chấp nhận cả username hoặc email)."""
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
