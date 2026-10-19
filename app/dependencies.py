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
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app import crud, permissions
from app.database import get_db
from app.models import Project, Tag, Task, User
from app.security import decode_access_token

# tokenUrl: endpoint đăng nhập -> Swagger UI dùng để hiện nút "Authorize"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/users/login")

DbSession = Annotated[Session, Depends(get_db)]


# ---------- Xác thực (Authentication): "Bạn là ai?" ----------
def get_current_user(token: Annotated[str, Depends(oauth2_scheme)], db: DbSession) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
        user_id = int(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        raise credentials_exception from None
    user = crud.user.get_by_id(db, user_id)
    if user is None:  # user đã bị xóa sau khi token được cấp
        raise credentials_exception
    return user


def get_current_active_user(user: Annotated[User, Depends(get_current_user)]) -> User:
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user")
    return user


CurrentUser = Annotated[User, Depends(get_current_active_user)]


# ---------- Phân quyền (Authorization): "Bạn được làm gì?" ----------
def verify_admin_role(user: CurrentUser) -> User:
    if not permissions.is_admin(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required"
        )
    return user


AdminUser = Annotated[User, Depends(verify_admin_role)]


def get_project_or_404(project_id: int, db: DbSession) -> Project:
    project = crud.project.get(db, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


def verify_project_manager(
    project: Annotated[Project, Depends(get_project_or_404)], user: CurrentUser
) -> Project:
    """Chỉ PM (owner) của project hoặc admin mới qua được. Trả về luôn project để endpoint dùng."""
    if not permissions.can_manage_project(user, project):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the project manager or an admin can perform this action",
        )
    return project


ManagedProject = Annotated[Project, Depends(verify_project_manager)]


# ---------- Load resource theo path param ----------
def get_task_or_404(task_id: int, db: DbSession) -> Task:
    task = crud.task.get(db, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


TaskDep = Annotated[Task, Depends(get_task_or_404)]


# ---------- Helper dùng chung cho router ----------
def load_tags_or_400(db: Session, tag_ids: list[int]) -> list[Tag]:
    """Body tham chiếu tới tag không tồn tại -> 400 (khác 404 dành cho resource trên URL)."""
    tags = crud.tag.get_many(db, tag_ids)
    missing = set(tag_ids) - {tag.id for tag in tags}
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tag ids not found: {sorted(missing)}",
        )
    return tags
