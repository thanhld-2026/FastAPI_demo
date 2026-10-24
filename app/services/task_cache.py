"""Cache Redis cho `GET /projects/{id}/tasks` (phụ lục feature 9).

Cache-aside có version, giống cache label (xem services/labels.py):
- Mỗi project 1 key version `taskhub:projects:{id}:tasks:version`.
- Mỗi tổ hợp filter + trang là 1 key dữ liệu có TTL, lưu sẵn chuỗi JSON của response:
  `taskhub:projects:{id}:tasks:v{n}:{schema}:status=..:priority=..:assignee=..:page=..:limit=..`
- Danh sách task của project đổi -> tăng version SAU khi commit: mọi tổ hợp filter / trang cũ
  cùng bị bỏ qua trong 1 lệnh (không phải tìm và xóa từng key), key cũ tự hết hạn theo TTL.

Tự động invalidate bằng event của SQLAlchemy Session, không gọi tay ở từng endpoint: danh sách
task đổi khi tạo / sửa / xóa / assign task, gắn / gỡ label, sửa / xóa label, xóa project, user đổi
tên, thành viên rời workspace (bỏ assign)... gọi tay ở từng chỗ rất dễ quên 1 chỗ.
- before_flush: dòng bị sửa / xóa qua ORM -> gom id project (lúc này dòng còn trong DB).
- after_flush: task mới -> gom id project (khóa ngoại project_id có sau khi INSERT).
- do_orm_execute: UPDATE / DELETE hàng loạt qua Session (vd crud.task.touch) -> gom id project
  của các dòng sắp bị đổi.
- after_commit: tăng version các project đã gom (1 pipeline Redis); after_rollback: bỏ danh sách.

Các event được đăng ký khi import app.models (xem cuối app/models/__init__.py): mọi process ghi
dữ liệu (API, script, worker) đều có, không phụ thuộc đã import service nào.
Giới hạn: thay đổi ngoài Session (câu SQL chạy thẳng trên connection, cascade trong DB như
`assignee_id ON DELETE SET NULL` khi xóa user) thì không thấy -> TTL là lưới an toàn.
"""

from collections.abc import Collection

from sqlalchemy import event, or_, select
from sqlalchemy.orm import ORMExecuteState, Session, UOWTransaction
from sqlalchemy.orm.attributes import instance_state

from app import cache
from app.config import settings
from app.models import Label, Project, Task, TaskPriority, TaskStatus, User
from app.schemas.common import Page
from app.schemas.task import TaskOut

_CHANGED = "task_cache_changed_projects"
_DELETED = "task_cache_deleted_projects"

# Đổi hình dạng TaskOut -> key mới (xem cache.schema_fingerprint)
_SCHEMA = cache.schema_fingerprint(Page[TaskOut])

# Quan hệ của Task không nằm trong TaskOut: đổi thì danh sách task không đổi (vd thêm comment).
# Mặc định là làm mới (thừa chỉ tốn 1 lần đọc DB), chỉ bỏ qua những gì chắc chắn không hiển thị.
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
    prefix = f"taskhub:projects:{project_id}:tasks:v{version}:{_SCHEMA}"
    return f"{prefix}:{filters}:page={page}:limit={limit}"


def current_version(project_id: int) -> int | None:
    """None: Redis tắt / lỗi -> không đọc, không ghi cache."""
    return cache.cache_version(_version_key(project_id))


def get_page(key: str) -> str | None:
    """Chuỗi JSON của response đã cache (trả thẳng cho client, không validate / serialize lại)."""
    return cache.cache_get_text(key)


def put_page(key: str, page_json: str) -> None:
    cache.cache_set_text(key, page_json, ttl=settings.TASKS_CACHE_TTL)


# ---------- Tự động invalidate theo event của Session ----------
def _enabled() -> bool:
    """Redis tắt (REDIS_URL rỗng) thì không cần theo dõi thay đổi (tránh việc + query thừa)."""
    return cache.get_redis() is not None


def _pending(session: Session) -> tuple[set[int], set[int]]:
    changed: set[int] = session.info.setdefault(_CHANGED, set())
    deleted: set[int] = session.info.setdefault(_DELETED, set())
    return changed, deleted


def _changed(obj: object, ignored: Collection[str]) -> bool:
    """Object có attribute (ngoài `ignored`) đổi giá trị trong lần flush này không.
    `history` không tự load attribute chưa load -> không phát sinh query."""
    return any(
        attr.history.has_changes() for attr in instance_state(obj).attrs if attr.key not in ignored
    )


def _projects_of_user_tasks(session: Session, user_id: int) -> set[int]:
    stmt = (
        select(Task.project_id)
        .where(or_(Task.creator_id == user_id, Task.assignee_id == user_id))
        .distinct()
    )
    # Đi thẳng qua connection: chạy query ORM trong lúc flush có thể kích hoạt autoflush lồng nhau
    return set(session.connection().scalars(stmt))


@event.listens_for(Session, "before_flush")
def _collect_changed_rows(session: Session, _flush: UOWTransaction, _instances: object) -> None:
    """Đọc `project_id` bằng attribute thường: nếu đã hết hạn (vd object được commit 1 lần rồi sửa
    tiếp) thì SQLAlchemy tự load lại. Phải làm TRƯỚC flush: sau flush dòng bị xóa không còn để load.
    """
    if not _enabled():
        return
    changed, deleted = _pending(session)
    for obj in session.deleted:
        if isinstance(obj, Task | Label):
            changed.add(obj.project_id)
        elif isinstance(obj, Project):
            deleted.add(obj.id)
    for obj in session.dirty:
        if isinstance(obj, Task) and _changed(obj, _TASK_ATTRS_NOT_LISTED):
            changed.add(obj.project_id)
        elif isinstance(obj, Label) and _changed(obj, {"tasks", "project"}):
            changed.add(obj.project_id)  # TaskOut có tên / màu label
        elif isinstance(obj, User) and instance_state(obj).attrs.full_name.history.has_changes():
            # TaskOut có full_name của người tạo / người được giao
            changed |= _projects_of_user_tasks(session, obj.id)


@event.listens_for(Session, "after_flush")
def _collect_new_tasks(session: Session, _flush: UOWTransaction) -> None:
    if not _enabled():
        return
    changed, _ = _pending(session)
    changed.update(obj.project_id for obj in session.new if isinstance(obj, Task))


@event.listens_for(Session, "do_orm_execute")
def _collect_bulk_statements(state: ORMExecuteState) -> None:
    """UPDATE / DELETE hàng loạt qua Session (`db.execute(update(Task)...)`) không đi qua unit of
    work nên before_flush không thấy: đọc project_id của các dòng sắp bị đổi bằng chính WHERE."""
    if not (state.is_update or state.is_delete) or not _enabled():
        return
    mapper = state.bind_mapper
    if mapper is None or mapper.class_ not in (Task, Label):
        return
    entity: type[Task] | type[Label] = mapper.class_
    affected = select(entity.project_id).distinct()
    where = state.statement.whereclause  # type: ignore[attr-defined]
    if where is not None:
        affected = affected.where(where)
    changed, _ = _pending(state.session)
    changed.update(state.session.connection().scalars(affected))


@event.listens_for(Session, "after_commit")
def _invalidate_after_commit(session: Session) -> None:
    deleted: set[int] = session.info.pop(_DELETED, set())
    changed: set[int] = session.info.pop(_CHANGED, set())
    versions: dict[str, int | None] = {_version_key(pid): None for pid in changed - deleted}
    # Project bị xóa: key version cũng tự hết hạn sau khi mọi key dữ liệu đã hết hạn
    versions.update({_version_key(pid): settings.TASKS_CACHE_TTL for pid in deleted})
    cache.cache_bump_versions(versions)


@event.listens_for(Session, "after_rollback")
def _forget_on_rollback(session: Session) -> None:
    session.info.pop(_CHANGED, None)
    session.info.pop(_DELETED, None)
