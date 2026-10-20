"""Các dependency dùng chung (hệ thống Dependency Injection của FastAPI).

Chuỗi phụ thuộc xác thực / phân quyền:

    oauth2_scheme  ->  get_current_user  ->  get_current_active_user  ->  verify_admin_role
    (lấy token)        (decode JWT,          (chặn user bị khóa)          (chỉ admin)
                        load user từ DB)                              ->  verify_project_manager
                                                                          (chỉ PM/admin của project)

Tương tự cho task / comment: verify_task_editor, verify_task_deleter, get_task_for_assign,
verify_comment_modifier.
Endpoint chỉ cần khai báo `current_user: CurrentUser` là FastAPI tự chạy cả chuỗi.
"""

from typing import Annotated

import jwt
from fastapi import Depends, Query
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app import crud, permissions
from app.core import messages
from app.core.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.core.exceptions import (
    BadRequestException,
    ForbiddenException,
    NotFoundException,
    UnauthorizedException,
)
from app.database import get_db
from app.models import Comment, Project, Tag, Task, User
from app.schemas.common import PageParams
from app.security import decode_access_token

# tokenUrl: endpoint đăng nhập -> Swagger UI dùng để hiện nút "Authorize"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/users/login")

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


# ---------- Phân quyền (Authorization): "Bạn được làm gì?" ----------
def verify_admin_role(user: CurrentUser) -> User:
    if not permissions.is_admin(user):
        raise ForbiddenException(messages.ADMIN_REQUIRED)
    return user


AdminUser = Annotated[User, Depends(verify_admin_role)]


def verify_project_manager(project: ProjectDep, user: CurrentUser) -> Project:
    """Chỉ PM (owner) của project hoặc admin mới qua được. Trả về luôn project để endpoint dùng."""
    if not permissions.can_manage_project(user, project):
        raise ForbiddenException(messages.PROJECT_MANAGER_REQUIRED)
    return project


ManagedProject = Annotated[Project, Depends(verify_project_manager)]


def verify_task_editor(task: TaskDep, user: CurrentUser) -> Task:
    """Người tạo / người được assign / PM / admin mới được sửa task."""
    if not permissions.can_edit_task(user, task):
        raise ForbiddenException(messages.TASK_EDIT_FORBIDDEN)
    return task


EditableTask = Annotated[Task, Depends(verify_task_editor)]


def verify_task_deleter(task: TaskDep, user: CurrentUser) -> Task:
    """Người tạo / PM / admin mới được xóa task."""
    if not permissions.can_delete_task(user, task):
        raise ForbiddenException(messages.TASK_DELETE_FORBIDDEN)
    return task


DeletableTask = Annotated[Task, Depends(verify_task_deleter)]


def get_task_for_assign(task_id: int, db: DbSession, user: CurrentUser) -> Task:
    """Khóa dòng task (SELECT ... FOR UPDATE) tới hết transaction rồi mới kiểm tra quyền:
    2 PM assign cùng 1 task cùng lúc thì request sau phải chờ request trước commit xong."""
    task = crud.task.get_for_update(db, task_id)
    if task is None:
        raise NotFoundException(messages.TASK_NOT_FOUND)
    if not permissions.can_manage_project(user, task.project):
        raise ForbiddenException(messages.TASK_ASSIGN_FORBIDDEN)
    return task


AssignableTask = Annotated[Task, Depends(get_task_for_assign)]


def verify_comment_modifier(
    task_id: int, comment_id: int, db: DbSession, user: CurrentUser
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
    skip: Annotated[int, Query(ge=0, description="Số bản ghi bỏ qua")] = 0,
    limit: Annotated[
        int, Query(ge=1, le=MAX_PAGE_SIZE, description="Số bản ghi tối đa của 1 trang")
    ] = DEFAULT_PAGE_SIZE,
) -> PageParams:
    return PageParams(skip=skip, limit=limit)


Pagination = Annotated[PageParams, Depends(get_pagination)]


# ---------- Helper dùng chung cho router ----------
def get_tags_by_ids(db: Session, tag_ids: list[int]) -> list[Tag]:
    """Body tham chiếu tới tag không tồn tại -> 400 (khác 404 dành cho resource trên URL)."""
    tags = crud.tag.get_many(db, tag_ids)
    missing = set(tag_ids) - {tag.id for tag in tags}
    if missing:
        raise BadRequestException(messages.TAG_IDS_NOT_FOUND.format(ids=sorted(missing)))
    return tags
