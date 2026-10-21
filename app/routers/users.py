from fastapi import APIRouter, Depends, status
from sqlalchemy.exc import IntegrityError

from app import crud
from app.core import messages
from app.core.exceptions import BadRequestException, ConflictException, NotFoundException
from app.core.responses import error_responses
from app.dependencies import AdminUser, CurrentUser, DbSession, Pagination, verify_admin_role
from app.models import UserRole
from app.schemas.common import Page
from app.schemas.profile import UserProfile
from app.schemas.task import TaskOut
from app.schemas.user import AdminUserUpdate, PasswordChange, UserOut, UserUpdate
from app.services import auth as auth_service

router = APIRouter(prefix="/users", tags=["Users"])


@router.get(
    "/me",
    response_model=UserOut,
    summary="Thông tin user đang đăng nhập",
    responses=error_responses(401, 403),
)
def read_me(current_user: CurrentUser):
    return current_user


@router.patch(
    "/me",
    response_model=UserOut,
    summary="Cập nhật thông tin cá nhân (chỉ field được gửi lên)",
    responses=error_responses(401, 403, 409),
)
def update_me(data: UserUpdate, current_user: CurrentUser, db: DbSession):
    email_taken = (
        data.email is not None
        and data.email.lower() != current_user.email
        and crud.user.get_by_email(db, data.email) is not None
    )
    if email_taken:
        raise ConflictException(messages.EMAIL_TAKEN)
    try:
        return crud.user.update(db, current_user, data)
    except IntegrityError:
        # 2 request đổi sang cùng 1 email gần như đồng thời -> UNIQUE trong DB chặn request sau
        db.rollback()
        raise ConflictException(messages.EMAIL_TAKEN) from None


@router.put(
    "/me/password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Đổi mật khẩu (đăng xuất mọi thiết bị khác)",
    responses=error_responses(400, 401, 403),
)
def change_password(data: PasswordChange, current_user: CurrentUser, db: DbSession):
    auth_service.change_password(db, current_user, data)


@router.get(
    "/me/bookmarks",
    response_model=Page[TaskOut],
    summary="Các task tôi đã bookmark",
    responses=error_responses(401, 403),
)
def my_bookmarks(current_user: CurrentUser, db: DbSession, pagination: Pagination):
    items, total = crud.task.list_bookmarked(db, current_user.id, pagination)
    return Page.build(items, total, pagination)


@router.get(
    "",
    response_model=Page[UserOut],
    # Không cần dùng giá trị trả về của dependency -> khai báo ở `dependencies=[...]`
    dependencies=[Depends(verify_admin_role)],
    summary="[Admin] Danh sách user",
    responses=error_responses(401, 403),
)
def list_users(db: DbSession, pagination: Pagination):
    items, total = crud.user.list_users(db, pagination)
    return Page.build(items, total, pagination)


@router.patch(
    "/{user_id}",
    response_model=UserOut,
    summary="[Admin] Đổi role / khóa tài khoản",
    responses=error_responses(400, 401, 403, 404),
)
def admin_update_user(user_id: int, data: AdminUserUpdate, admin: AdminUser, db: DbSession):
    user = crud.user.get_by_id(db, user_id)
    if user is None:
        raise NotFoundException(messages.USER_NOT_FOUND)
    # So với ADMIN thay vì MEMBER: sau này thêm role mới thì vẫn chặn được việc tự hạ quyền
    demote_or_deactivate = data.role not in (None, UserRole.ADMIN) or data.is_active is False
    if user.id == admin.id and demote_or_deactivate:
        raise BadRequestException(messages.ADMIN_CANNOT_DEMOTE_SELF)
    return crud.user.admin_update(db, user, data)


@router.get(
    "/{username}/profile",
    response_model=UserProfile,
    summary="Trang cá nhân công khai",
    responses=error_responses(404),
)
def get_profile(username: str, db: DbSession):
    user = crud.user.get_profile(db, username)
    if user is None:
        raise NotFoundException(messages.USER_NOT_FOUND)
    return user
