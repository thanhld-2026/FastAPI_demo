from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.exc import IntegrityError

from app import crud
from app.core import messages
from app.core.exceptions import (
    BadRequestException,
    ConflictException,
    ForbiddenException,
    NotFoundException,
    UnauthorizedException,
)
from app.dependencies import AdminUser, CurrentUser, DbSession, verify_admin_role
from app.models import UserRole
from app.schemas.common import Page
from app.schemas.profile import UserProfile
from app.schemas.task import TaskOut
from app.schemas.user import AdminUserUpdate, Token, UserCreate, UserOut, UserUpdate
from app.security import create_access_token

router = APIRouter(prefix="/api/users", tags=["Users"])


@router.post(
    "/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Đăng ký tài khoản",
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


@router.post("/login", response_model=Token, summary="Đăng nhập (trả về access_token)")
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], db: DbSession):
    """Chuẩn OAuth2 Password Flow: gửi **form data** `username` + `password`
    (field `username` chấp nhận cả username hoặc email)."""
    user = crud.user.authenticate(db, form.username, form.password)
    if user is None:
        raise UnauthorizedException(messages.INCORRECT_LOGIN)
    if not user.is_active:
        raise ForbiddenException(messages.INACTIVE_USER)
    return Token(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserOut, summary="Thông tin user đang đăng nhập")
def read_me(current_user: CurrentUser):
    return current_user


@router.put("/me", response_model=UserOut, summary="Cập nhật thông tin cá nhân")
def update_me(data: UserUpdate, current_user: CurrentUser, db: DbSession):
    email_changed = data.email and data.email.lower() != current_user.email
    if email_changed and crud.user.get_by_email(db, data.email):
        raise ConflictException(messages.EMAIL_TAKEN)
    return crud.user.update(db, current_user, data)


@router.get("/me/bookmarks", response_model=list[TaskOut], summary="Các task tôi đã bookmark")
def my_bookmarks(current_user: CurrentUser, db: DbSession):
    return crud.task.list_bookmarked(db, current_user.id)


@router.get(
    "",
    response_model=Page[UserOut],
    # Không cần dùng giá trị trả về của dependency -> khai báo ở `dependencies=[...]`
    dependencies=[Depends(verify_admin_role)],
    summary="[Admin] Danh sách user",
)
def list_users(
    db: DbSession,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    items, total = crud.user.list_users(db, skip=skip, limit=limit)
    return {"items": items, "total": total, "skip": skip, "limit": limit}


@router.patch("/{user_id}", response_model=UserOut, summary="[Admin] Đổi role / khóa tài khoản")
def admin_update_user(user_id: int, data: AdminUserUpdate, admin: AdminUser, db: DbSession):
    user = crud.user.get_by_id(db, user_id)
    if user is None:
        raise NotFoundException(messages.USER_NOT_FOUND)
    if user.id == admin.id and (data.role == UserRole.MEMBER or data.is_active is False):
        raise BadRequestException(messages.ADMIN_CANNOT_DEMOTE_SELF)
    return crud.user.admin_update(db, user, data)


@router.get("/{username}/profile", response_model=UserProfile, summary="Trang cá nhân công khai")
def get_profile(username: str, db: DbSession):
    user = crud.user.get_profile(db, username)
    if user is None:
        raise NotFoundException(messages.USER_NOT_FOUND)
    return user
