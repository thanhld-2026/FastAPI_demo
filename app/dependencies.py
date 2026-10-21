"""Các dependency dùng chung (hệ thống Dependency Injection của FastAPI).

Chuỗi phụ thuộc xác thực / phân quyền:

    oauth2_scheme  ->  get_current_user  ->  get_current_active_user  ->  verify_admin_role
    (lấy token)        (decode JWT,          (chặn user bị khóa)          (chỉ admin)
                        load user từ DB)                              ->  verify_project_manager
                                                                          (chỉ PM/admin của project)

Tương tự cho task / comment: verify_task_editor, verify_task_deleter, get_task_for_assign,
verify_comment_modifier. Endpoint ghi dùng WritableProject / WritableTask / ChangeableProject
(project đã archive -> 409), xem phần "Load resource để GHI".
Endpoint chỉ cần khai báo `current_user: CurrentUser` là FastAPI tự chạy cả chuỗi.
"""

from typing import Annotated

import jwt
from fastapi import Depends, Query
from fastapi.exceptions import RequestValidationError
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app import crud, permissions
from app.core import messages
from app.core.constants import API_V1_PREFIX, DEFAULT_PAGE_SIZE, MAX_PAGE, MAX_PAGE_SIZE
from app.core.exceptions import (
    BadRequestException,
    ConflictException,
    ForbiddenException,
    NotFoundException,
    UnauthorizedException,
)
from app.database import get_db
from app.models import Comment, Project, ProjectStatus, Tag, Task, User
from app.schemas.common import PageParams
from app.security import decode_access_token

# tokenUrl: endpoint đăng nhập -> Swagger UI dùng để hiện nút "Authorize"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{API_V1_PREFIX}/auth/login")

DbSession = Annotated[Session, Depends(get_db)]


# ---------- Xác thực (Authentication): "Bạn là ai?" ----------
def get_current_user(token: Annotated[str, Depends(oauth2_scheme)], db: DbSession) -> User:
    try:
        payload = decode_access_token(token)
        user_id = int(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        raise UnauthorizedException(messages.INVALID_CREDENTIALS) from None
    user = crud.user.get_by_id(db, user_id)
    if user is None:  # user đã bị xóa sau khi token được cấp
        raise UnauthorizedException(messages.INVALID_CREDENTIALS)
    return user


def get_current_active_user(user: Annotated[User, Depends(get_current_user)]) -> User:
    if not user.is_active:
        raise ForbiddenException(messages.INACTIVE_USER)
    return user


CurrentUser = Annotated[User, Depends(get_current_active_user)]


# ---------- Load resource theo path param ----------
def get_existing_project(project_id: int, db: DbSession) -> Project:
    project = crud.project.get(db, project_id)
    if project is None:
        raise NotFoundException(messages.PROJECT_NOT_FOUND)
    return project


ProjectDep = Annotated[Project, Depends(get_existing_project)]


def get_existing_task(task_id: int, db: DbSession) -> Task:
    task = crud.task.get(db, task_id)
    if task is None:
        raise NotFoundException(messages.TASK_NOT_FOUND)
    return task


TaskDep = Annotated[Task, Depends(get_existing_task)]


def ensure_task_exists(task_id: int, db: DbSession) -> int:
    """Chỉ kiểm tra task có tồn tại (query EXISTS), không load cả task + quan hệ như
    get_existing_task. Dùng cho API chỉ cần task_id, ví dụ bookmark."""
    if not crud.task.exists_by_id(db, task_id):
        raise NotFoundException(messages.TASK_NOT_FOUND)
    return task_id


ExistingTaskId = Annotated[int, Depends(ensure_task_exists)]


def get_existing_tag(tag_id: int, db: DbSession) -> Tag:
    tag = crud.tag.get(db, tag_id)
    if tag is None:
        raise NotFoundException(messages.TAG_NOT_FOUND)
    return tag


TagDep = Annotated[Tag, Depends(get_existing_tag)]


# ---------- Load resource để GHI: project phải đang ACTIVE ----------
# Quy ước: endpoint ghi vào project / task / comment chỉ dùng các dependency trong phần này
# (hoặc các dependency phân quyền dựng trên chúng); endpoint đọc dùng ProjectDep / TaskDep.
# Nhờ vậy quy tắc "project đã archive thì chỉ đọc" chỉ nằm ở _ensure_project_writable.
def _raise_if_not_writable(status: ProjectStatus | None, not_found_message: str) -> None:
    if status is None:  # không tồn tại / vừa bị xóa bởi request khác
        raise NotFoundException(not_found_message)
    if status == ProjectStatus.ARCHIVED:
        raise ConflictException(messages.PROJECT_ARCHIVED)


def _ensure_project_writable(db: Session, project_id: int, *, exclusive: bool = False) -> None:
    status = crud.project.lock_status(db, project_id, exclusive=exclusive)
    _raise_if_not_writable(status, messages.PROJECT_NOT_FOUND)


def get_writable_project(project: ProjectDep, db: DbSession) -> Project:
    """Project nhận thêm dữ liệu (vd tạo task): khóa chia sẻ dòng project."""
    _ensure_project_writable(db, project.id)
    return project


WritableProject = Annotated[Project, Depends(get_writable_project)]


def get_writable_task(task: TaskDep, db: DbSession) -> Task:
    """Task được sửa / xóa / assign / comment: project chứa nó phải đang ACTIVE."""
    _ensure_project_writable(db, task.project_id)
    return task


WritableTask = Annotated[Task, Depends(get_writable_task)]


def get_writable_task_id(task_id: int, db: DbSession) -> int:
    """Như WritableTask nhưng chỉ cần task_id (sửa / xóa comment): 1 query, không load cả task."""
    _raise_if_not_writable(crud.task.lock_project_status(db, task_id), messages.TASK_NOT_FOUND)
    return task_id


WritableTaskId = Annotated[int, Depends(get_writable_task_id)]


# ---------- Phân quyền (Authorization): "Bạn được làm gì?" ----------
# Thứ tự lỗi: 401 (chưa đăng nhập) -> 404 (không có resource) -> 409 (project đã archive)
# -> 403 (không đủ quyền). Tham số `user` luôn khai báo trước để 401 được kiểm tra đầu tiên;
# 409 trước 403 không lộ gì vì status của project vốn công khai (GET project).
def verify_admin_role(user: CurrentUser) -> User:
    if not permissions.is_admin(user):
        raise ForbiddenException(messages.ADMIN_REQUIRED)
    return user


AdminUser = Annotated[User, Depends(verify_admin_role)]


def _require_project_manager(user: User, project: Project) -> None:
    if not permissions.can_manage_project(user, project):
        raise ForbiddenException(messages.PROJECT_MANAGER_REQUIRED)


def verify_project_manager(user: CurrentUser, project: ProjectDep) -> Project:
    """Archive / unarchive: chỉ PM (owner) của project hoặc admin, ở trạng thái nào cũng được."""
    _require_project_manager(user, project)
    return project


ManagedProject = Annotated[Project, Depends(verify_project_manager)]


def get_project_for_change(user: CurrentUser, project: ProjectDep, db: DbSession) -> Project:
    """Sửa / xóa project: khóa độc quyền dòng project, project phải ACTIVE, user là PM / admin."""
    _ensure_project_writable(db, project.id, exclusive=True)
    _require_project_manager(user, project)
    return project


ChangeableProject = Annotated[Project, Depends(get_project_for_change)]


def verify_task_editor(user: CurrentUser, task: WritableTask) -> Task:
    """Người tạo / người được assign / PM / admin mới được sửa task."""
    if not permissions.can_edit_task(user, task):
        raise ForbiddenException(messages.TASK_EDIT_FORBIDDEN)
    return task


EditableTask = Annotated[Task, Depends(verify_task_editor)]


def verify_task_deleter(user: CurrentUser, task: WritableTask) -> Task:
    """Người tạo / PM / admin mới được xóa task."""
    if not permissions.can_delete_task(user, task):
        raise ForbiddenException(messages.TASK_DELETE_FORBIDDEN)
    return task


DeletableTask = Annotated[Task, Depends(verify_task_deleter)]


def get_task_for_assign(user: CurrentUser, task: WritableTask, db: DbSession) -> Task:
    """Khóa thêm dòng task (SELECT ... FOR UPDATE) tới hết transaction rồi mới kiểm tra quyền:
    2 PM assign cùng 1 task cùng lúc thì request sau phải chờ request trước commit xong."""
    locked = crud.task.get_for_update(db, task.id)
    if locked is None:  # task vừa bị xóa bởi request khác
        raise NotFoundException(messages.TASK_NOT_FOUND)
    if not permissions.can_manage_project(user, locked.project):
        raise ForbiddenException(messages.TASK_ASSIGN_FORBIDDEN)
    return locked


AssignableTask = Annotated[Task, Depends(get_task_for_assign)]


def verify_comment_modifier(
    user: CurrentUser, task_id: WritableTaskId, comment_id: int, db: DbSession
) -> Comment:
    """Chỉ tác giả comment, PM của project hoặc admin mới được sửa / xóa.
    Lọc theo cả task_id để chặn truy cập chéo: /tasks/1/comments/<id comment của task 2>."""
    comment = crud.comment.get(db, task_id=task_id, comment_id=comment_id)
    if comment is None:
        raise NotFoundException(messages.COMMENT_NOT_FOUND)
    if not permissions.can_modify_comment(user, comment):
        raise ForbiddenException(messages.COMMENT_MODIFY_FORBIDDEN)
    return comment


ModifiableComment = Annotated[Comment, Depends(verify_comment_modifier)]


# ---------- Phân trang ----------
def get_pagination(
    page: Annotated[int, Query(ge=1, le=MAX_PAGE, description="Số trang, bắt đầu từ 1")] = 1,
    limit: Annotated[
        int, Query(ge=1, le=MAX_PAGE_SIZE, description="Số bản ghi tối đa của 1 trang")
    ] = DEFAULT_PAGE_SIZE,
    skip: Annotated[str | None, Query(include_in_schema=False)] = None,
) -> PageParams:
    if skip is not None:
        # Tham số cũ (trước /api/v1): FastAPI mặc định bỏ qua query param lạ -> client cũ gửi
        # ?skip=20 sẽ luôn nhận trang 1 (vòng lặp phân trang chạy mãi). Báo lỗi 422 rõ ràng.
        raise RequestValidationError(
            [
                {
                    "type": "extra_forbidden",
                    "loc": ("query", "skip"),
                    "msg": messages.SKIP_PARAM_REMOVED,
                    "input": skip,
                }
            ]
        )
    return PageParams(page=page, limit=limit)


Pagination = Annotated[PageParams, Depends(get_pagination)]


# ---------- Helper dùng chung cho router ----------
def get_tags_by_ids(db: Session, tag_ids: list[int]) -> list[Tag]:
    """Body tham chiếu tới tag không tồn tại -> 400 (khác 404 dành cho resource trên URL)."""
    tags = crud.tag.get_many(db, tag_ids)
    missing = set(tag_ids) - {tag.id for tag in tags}
    if missing:
        raise BadRequestException(messages.TAG_IDS_NOT_FOUND.format(ids=sorted(missing)))
    return tags
