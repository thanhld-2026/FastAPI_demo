"""Các dependency dùng chung (hệ thống Dependency Injection của FastAPI).

Chuỗi phụ thuộc xác thực / phân quyền:

    oauth2_scheme  ->  get_current_user  ->  get_current_active_user  ->  verify_admin_role
    (lấy token)        (decode JWT,          (chặn user bị khóa)          (chỉ admin)
                        load user từ DB)                              ->  verify_project_manager
                                                                          (chỉ PM/admin của project)

Endpoint chỉ cần khai báo `current_user: CurrentUser` là FastAPI tự chạy cả chuỗi.
"""

from typing import Annotated

import jwt
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app import crud, permissions
from app.core import messages
from app.core.exceptions import (
    BadRequestException,
    ForbiddenException,
    NotFoundException,
    UnauthorizedException,
)
from app.database import get_db
from app.models import Project, Tag, Task, User
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


# ---------- Helper dùng chung cho router ----------
def get_tags_by_ids(db: Session, tag_ids: list[int]) -> list[Tag]:
    """Body tham chiếu tới tag không tồn tại -> 400 (khác 404 dành cho resource trên URL)."""
    tags = crud.tag.get_many(db, tag_ids)
    missing = set(tag_ids) - {tag.id for tag in tags}
    if missing:
        raise BadRequestException(messages.TAG_IDS_NOT_FOUND.format(ids=sorted(missing)))
    return tags
