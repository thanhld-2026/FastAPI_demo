"""Cache Redis cho `GET /projects/{id}/tasks` (phụ lục feature 9).

Cache-aside có version, giống cache label (xem services/labels.py):
- Mỗi project 1 key version `taskhub:projects:{id}:tasks:version`.
- Mỗi tổ hợp filter + trang là 1 key dữ liệu có TTL:
  `taskhub:projects:{id}:tasks:v{n}:status=..:priority=..:assignee=..:page=..:limit=..`
- Danh sách task của project đổi -> tăng version SAU khi commit: mọi tổ hợp filter / trang cũ
  cùng bị bỏ qua trong 1 lệnh (không phải tìm và xóa từng key), key cũ tự hết hạn theo TTL.

Tự động invalidate bằng event của SQLAlchemy Session, không gọi tay ở từng endpoint: danh sách
task đổi khi tạo / sửa / xóa / assign task, gắn / gỡ label, sửa / xóa label, xóa project, user đổi
tên, thành viên rời workspace (bỏ assign)... gọi tay ở từng chỗ rất dễ quên 1 chỗ.
- after_flush: xem các object vừa ghi xuống DB, gom id các project có danh sách task bị ảnh hưởng.
- after_commit: tăng version các project đó (đúng lúc dữ liệu mới đã commit).
- after_rollback: bỏ danh sách đã gom (không có gì được lưu).
"""

from collections.abc import Collection
from typing import Any

from sqlalchemy import event, or_, select
from sqlalchemy.orm import Session, UOWTransaction
from sqlalchemy.orm.attributes import instance_state

from app.cache import cache_bump_version, cache_get, cache_set, cache_version
from app.config import settings
from app.models import Label, Project, Task, TaskPriority, TaskStatus, User

_CHANGED = "task_cache_changed_projects"
_DELETED = "task_cache_deleted_projects"

# Quan hệ của Task không nằm trong TaskOut: đổi thì danh sách task không đổi (vd thêm comment)
_TASK_ATTRS_NOT_LISTED = {"comments", "activities", "bookmarked_by", "project"}


def _version_key(project_id: int) -> str:
    return f"taskhub:projects:{project_id}:tasks:version"


def page_key(
    project_id: int,
    version: int,
    *,
    status: TaskStatus | None,
    priority: TaskPriority | None,
    assignee_id: int | None,
    page: int,
    limit: int,
) -> str:
    filters = f"status={status or ''}:priority={priority or ''}:assignee={assignee_id or ''}"
    return f"taskhub:projects:{project_id}:tasks:v{version}:{filters}:page={page}:limit={limit}"


def current_version(project_id: int) -> int | None:
    """None: Redis tắt / lỗi -> không đọc, không ghi cache."""
    return cache_version(_version_key(project_id))


def get(key: str) -> dict[str, Any] | None:
    return cache_get(key)


def put(key: str, page: dict[str, Any]) -> None:
    cache_set(key, page, ttl=settings.TASKS_CACHE_TTL)


# ---------- Tự động invalidate theo event của Session ----------
def _changed(obj: object, ignored: Collection[str]) -> bool:
    """Object có attribute (ngoài `ignored`) đổi giá trị trong lần flush này không.
    `history` không tự load attribute chưa load -> không phát sinh query."""
    return any(
        attr.history.has_changes() for attr in instance_state(obj).attrs if attr.key not in ignored
    )


def _loaded(obj: object, name: str) -> Any:
    """Giá trị attribute đã có trong object, không tự load (object có thể vừa bị xóa)."""
    return instance_state(obj).dict.get(name)


def _projects_of_user_tasks(session: Session, user_id: int) -> set[int]:
    stmt = (
        select(Task.project_id)
        .where(or_(Task.creator_id == user_id, Task.assignee_id == user_id))
        .distinct()
    )
    # Đi thẳng qua connection: chạy query ORM trong lúc flush có thể kích hoạt autoflush lồng nhau
    return set(session.connection().scalars(stmt))


@event.listens_for(Session, "after_flush")
def _collect_changed_projects(session: Session, _flush: UOWTransaction) -> None:
    changed: set[int] = session.info.setdefault(_CHANGED, set())
    deleted: set[int] = session.info.setdefault(_DELETED, set())
    for obj in session.new:
        if isinstance(obj, Task):
            changed.add(_loaded(obj, "project_id"))
    for obj in session.deleted:
        if isinstance(obj, Task | Label):
            changed.add(_loaded(obj, "project_id"))
        elif isinstance(obj, Project):
            deleted.add(_loaded(obj, "id"))
    for obj in session.dirty:
        if isinstance(obj, Task) and _changed(obj, _TASK_ATTRS_NOT_LISTED):
            changed.add(_loaded(obj, "project_id"))
        elif isinstance(obj, Label) and _changed(obj, {"tasks", "project"}):
            changed.add(_loaded(obj, "project_id"))  # TaskOut có tên / màu label
        elif isinstance(obj, User) and instance_state(obj).attrs.full_name.history.has_changes():
            # TaskOut có full_name của người tạo / người được giao
            changed |= _projects_of_user_tasks(session, _loaded(obj, "id"))


@event.listens_for(Session, "after_commit")
def _invalidate_after_commit(session: Session) -> None:
    deleted: set[int] = session.info.pop(_DELETED, set())
    changed: set[int] = session.info.pop(_CHANGED, set())
    for project_id in changed - deleted:
        cache_bump_version(_version_key(project_id))
    for project_id in deleted:
        # Project bị xóa: key version cũng tự hết hạn sau khi mọi key dữ liệu đã hết hạn
        cache_bump_version(_version_key(project_id), ttl=settings.TASKS_CACHE_TTL)


@event.listens_for(Session, "after_rollback")
def _forget_on_rollback(session: Session) -> None:
    session.info.pop(_CHANGED, None)
    session.info.pop(_DELETED, None)
