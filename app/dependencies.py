"""Các dependency dùng chung (hệ thống Dependency Injection của FastAPI).

Xác thực:

    oauth2_scheme  ->  get_current_user  ->  get_current_active_user  ->  verify_admin_role
    (lấy token)        (decode JWT,          (chặn user bị khóa)          (chỉ admin hệ thống)
                        load user từ DB)

Phân quyền theo workspace (RBAC, quy tắc trong permissions.py): mỗi endpoint khai báo resource
nó cần kèm mức quyền, ví dụ `task: EditableTask`, FastAPI tự chạy cả chuỗi:
load resource -> kiểm tra thành viên -> project còn ACTIVE (nếu là thao tác ghi) -> đủ role.
"""

from collections.abc import Callable
from functools import partial
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
from app.models import (
    Comment,
    Label,
    Project,
    ProjectStatus,
    Task,
    User,
    Workspace,
    WorkspaceRole,
)
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


# ---------- Admin hệ thống ----------
def verify_admin_role(user: CurrentUser) -> User:
    if not permissions.is_admin(user):
        raise ForbiddenException(messages.ADMIN_REQUIRED)
    return user


AdminUser = Annotated[User, Depends(verify_admin_role)]


# ---------- Phân quyền theo workspace ----------
# Thứ tự lỗi: 401 (chưa đăng nhập) -> 404 (không tồn tại HOẶC không phải thành viên: người ngoài
# không biết được resource có tồn tại hay không) -> 409 (project đã archive, chỉ với thao tác
# ghi) -> 403 (là thành viên nhưng role không đủ). Tham số `user` khai báo trước để 401 luôn
# được kiểm tra đầu tiên.
def _require_member(user: User, role: WorkspaceRole | None, not_found_message: str) -> None:
    if role is None and not permissions.is_admin(user):
        raise NotFoundException(not_found_message)


def _require_role(user: User, role: WorkspaceRole | None, minimum: WorkspaceRole) -> None:
    if not permissions.has_role(user, role, minimum):
        raise ForbiddenException(messages.WORKSPACE_ROLE_REQUIRED.format(role=minimum.value))


def _raise_if_not_writable(status: ProjectStatus | None, not_found_message: str) -> None:
    """Quy tắc "project đã archive thì project, task, comment bên trong chỉ đọc" chỉ nằm ở đây."""
    if status is None:  # không tồn tại / vừa bị xóa bởi request khác
        raise NotFoundException(not_found_message)
    if status == ProjectStatus.ARCHIVED:
        raise ConflictException(messages.PROJECT_ARCHIVED)


def _authorize(
    user: User,
    role: WorkspaceRole | None,
    minimum: WorkspaceRole,
    not_found_message: str,
    read_status: Callable[[], ProjectStatus | None] | None = None,
) -> None:
    """Thứ tự kiểm tra dùng chung cho project / task / label: 404 (không phải thành viên)
    -> 409 (project đã archive, chỉ với thao tác ghi: có `read_status`) -> 403 (role không đủ).

    read_status là hàm: chỉ đọc (và khóa) status project SAU khi biết user là thành viên.
    """
    _require_member(user, role, not_found_message)
    if read_status is not None:
        _raise_if_not_writable(read_status(), not_found_message)
    _require_role(user, role, minimum)


def workspace_access(minimum: WorkspaceRole) -> Callable[..., Workspace]:
    """Dependency có tham số (factory): workspace trên URL + user phải có ít nhất role `minimum`."""

    def dependency(workspace_id: int, user: CurrentUser, db: DbSession) -> Workspace:
        workspace = crud.workspace.get(db, workspace_id)
        if workspace is None:
            raise NotFoundException(messages.WORKSPACE_NOT_FOUND)
        role = crud.workspace.get_role(db, workspace_id, user.id)
        _require_member(user, role, messages.WORKSPACE_NOT_FOUND)
        _require_role(user, role, minimum)
        return workspace

    return dependency


ReadableWorkspace = Annotated[Workspace, Depends(workspace_access(WorkspaceRole.VIEWER))]
OwnedWorkspace = Annotated[Workspace, Depends(workspace_access(WorkspaceRole.OWNER))]


def _lock_project(db: Session, project_id: int) -> Project:
    project = crud.project.get_for_update(db, project_id)
    if project is None:  # vừa bị xóa bởi request khác
        raise NotFoundException(messages.PROJECT_NOT_FOUND)
    return project


def project_access(
    minimum: WorkspaceRole, *, writable: bool = False, lock: bool = False
) -> Callable[..., Project]:
    """Project trên URL + user có ít nhất role `minimum` trong workspace chứa project.

    writable: project phải ACTIVE. Status đọc bằng SELECT ... FOR SHARE (crud.project.lock_status)
        để archive không chen vào giữa lúc đang ghi task / comment.
    lock: request sẽ sửa / xóa chính dòng project -> SELECT ... FOR UPDATE và đọc lại project.
        Chỉ khóa SAU khi đã kiểm tra quyền: người không có quyền không giữ được khóa.
    """

    def dependency(project_id: int, user: CurrentUser, db: DbSession) -> Project:
        found = crud.project.get(db, project_id)
        if found is None:
            raise NotFoundException(messages.PROJECT_NOT_FOUND)

        def read_status() -> ProjectStatus | None:
            # lock=True: chưa khóa ở bước này (khóa sau khi đủ quyền), chỉ để 409 đứng trước 403
            return found.status if lock else crud.project.lock_status(db, found.id)

        role = crud.workspace.get_role(db, found.workspace_id, user.id)
        _authorize(
            user, role, minimum, messages.PROJECT_NOT_FOUND, read_status if writable else None
        )
        if not lock:
            return found
        project = _lock_project(db, found.id)
        if writable:  # status có thể đã đổi trong lúc chờ khóa
            _raise_if_not_writable(project.status, messages.PROJECT_NOT_FOUND)
        return project

    return dependency


ReadableProject = Annotated[Project, Depends(project_access(WorkspaceRole.VIEWER))]
# Thêm task vào project (EDITOR, project ACTIVE)
EditableProject = Annotated[
    Project, Depends(project_access(WorkspaceRole.EDITOR, writable=True))
]
# Archive / unarchive (OWNER, project ở trạng thái nào cũng được)
ManagedProject = Annotated[Project, Depends(project_access(WorkspaceRole.OWNER, lock=True))]
# Sửa / xóa chính project (OWNER, project ACTIVE)
ChangeableProject = Annotated[
    Project, Depends(project_access(WorkspaceRole.OWNER, writable=True, lock=True))
]


def task_access(
    minimum: WorkspaceRole,
    *,
    writable: bool = False,
    lock: bool = False,
    for_delete: bool = False,
) -> Callable[..., Task]:
    """Task trên URL + user có ít nhất role `minimum` trong workspace chứa task.

    writable: project chứa task phải ACTIVE (FOR SHARE, giống project_access).
    lock: khóa dòng task (FOR UPDATE) sau khi kiểm tra quyền, vd 2 người assign cùng 1 task
        cùng lúc thì request sau chờ request trước commit xong.
    for_delete: thêm quy tắc xóa task (EDITOR chỉ xóa task mình tạo), dùng luôn role đã đọc.
    """

    def dependency(task_id: int, user: CurrentUser, db: DbSession) -> Task:
        # 1 query JOIN lấy role; None = task không tồn tại HOẶC không phải thành viên
        role = crud.workspace.get_role_for_task(db, task_id, user.id)
        read_status = partial(crud.task.lock_project_status, db, task_id) if writable else None
        _authorize(user, role, minimum, messages.TASK_NOT_FOUND, read_status)
        task = crud.task.get_for_update(db, task_id) if lock else crud.task.get(db, task_id)
        if task is None:  # admin xem task không tồn tại, hoặc task vừa bị xóa
            raise NotFoundException(messages.TASK_NOT_FOUND)
        if for_delete and not permissions.can_delete_task(user, role, task):
            raise ForbiddenException(messages.TASK_DELETE_FORBIDDEN)
        return task

    return dependency


ReadableTask = Annotated[Task, Depends(task_access(WorkspaceRole.VIEWER))]
EditableTask = Annotated[Task, Depends(task_access(WorkspaceRole.EDITOR, writable=True))]
AssignableTask = Annotated[
    Task, Depends(task_access(WorkspaceRole.EDITOR, writable=True, lock=True))
]
# EDITOR chỉ xóa task mình tạo; OWNER / admin xóa được mọi task
DeletableTask = Annotated[
    Task, Depends(task_access(WorkspaceRole.EDITOR, writable=True, for_delete=True))
]


def label_access(
    minimum: WorkspaceRole, *, writable: bool = False, lock: bool = False
) -> Callable[..., Label]:
    """Label trên URL + role tối thiểu trong workspace chứa project của label.

    lock: sửa / xóa chính label -> FOR UPDATE + đọc lại sau khi kiểm tra quyền (như project).
    """

    def dependency(label_id: int, user: CurrentUser, db: DbSession) -> Label:
        label = crud.label.get(db, label_id)
        if label is None:
            raise NotFoundException(messages.LABEL_NOT_FOUND)
        role = crud.workspace.get_role_for_project(db, label.project_id, user.id)
        read_status = partial(crud.project.lock_status, db, label.project_id) if writable else None
        _authorize(user, role, minimum, messages.LABEL_NOT_FOUND, read_status)
        if lock:
            locked = crud.label.get_for_update(db, label.id)
            if locked is None:  # vừa bị xóa bởi request khác
                raise NotFoundException(messages.LABEL_NOT_FOUND)
            label = locked
        return label

    return dependency


EditableLabel = Annotated[
    Label, Depends(label_access(WorkspaceRole.EDITOR, writable=True, lock=True))
]


def get_readable_task_id(task_id: int, user: CurrentUser, db: DbSession) -> int:
    """Như ReadableTask nhưng chỉ cần task_id (bookmark, danh sách comment / activity):
    1 query JOIN lấy role, không load cả task."""
    role = crud.workspace.get_role_for_task(db, task_id, user.id)
    # role None = task không tồn tại HOẶC không phải thành viên; admin thì phải kiểm tra tồn tại
    if role is None and not (permissions.is_admin(user) and crud.task.exists_by_id(db, task_id)):
        raise NotFoundException(messages.TASK_NOT_FOUND)
    return task_id


ReadableTaskId = Annotated[int, Depends(get_readable_task_id)]


def verify_comment_modifier(
    task_id: int, comment_id: int, user: CurrentUser, db: DbSession
) -> Comment:
    """Sửa / xóa comment: tác giả (còn quyền EDITOR) hoặc OWNER / admin.
    Lọc theo cả task_id để chặn truy cập chéo: /tasks/1/comments/<id comment của task 2>."""
    role = crud.workspace.get_role_for_task(db, task_id, user.id)
    _require_member(user, role, messages.TASK_NOT_FOUND)
    comment = crud.comment.get(db, task_id=task_id, comment_id=comment_id)
    if comment is None:  # 404 đứng trước 409 / 403
        raise NotFoundException(messages.COMMENT_NOT_FOUND)
    _raise_if_not_writable(crud.task.lock_project_status(db, task_id), messages.TASK_NOT_FOUND)
    _require_role(user, role, WorkspaceRole.EDITOR)
    if not permissions.can_modify_comment(user, role, comment):
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
def get_labels_by_ids(db: Session, project_id: int, label_ids: list[int]) -> list[Label]:
    """Body tham chiếu label không tồn tại / thuộc project khác -> 400 (404 dành cho URL).
    Khóa chia sẻ các label tới hết request: không bị xóa trong lúc đang gắn vào task."""
    labels = crud.label.get_many_in_project(db, project_id, label_ids, for_share=True)
    missing = set(label_ids) - {label.id for label in labels}
    if missing:
        raise BadRequestException(messages.LABEL_IDS_NOT_FOUND.format(ids=sorted(missing)))
    return labels
