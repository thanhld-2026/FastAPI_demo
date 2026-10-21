from sqlalchemy import ColumnElement, Select, exists, func, insert, select
from sqlalchemy import delete as sql_delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from app.crud import activity as activity_crud
from app.crud.workspace import member_workspace_ids
from app.models import (
    ActivityAction,
    Project,
    ProjectStatus,
    Tag,
    Task,
    TaskPriority,
    TaskStatus,
    User,
    task_bookmarks,
)
from app.schemas.common import PageParams
from app.schemas.task import TaskCreate, TaskUpdate

# Eager loading dùng chung cho mọi query trả về TaskOut.
# Không có dòng này: trả về 20 task -> 1 query lấy task + 20 query creator
# + 20 query assignee + 20 query tags = 61 query (N+1 problem).
# Có dòng này: luôn chỉ 2 query (task JOIN users, và 1 query lấy tags).
TASK_LOAD_OPTIONS = (
    joinedload(Task.creator),  # Many-to-One -> LEFT OUTER JOIN
    joinedload(Task.assignee),  # Many-to-One -> LEFT OUTER JOIN
    selectinload(Task.tags),  # Many-to-Many -> SELECT ... WHERE task_id IN (...)
)


def _select_task(task_id: int) -> Select[Task]:
    return select(Task).where(Task.id == task_id).options(*TASK_LOAD_OPTIONS)


def get(db: Session, task_id: int) -> Task | None:
    return db.scalar(_select_task(task_id))


def _reload(db: Session, task_id: int) -> Task:
    """Đọc lại task vừa ghi (chắc chắn tồn tại) kèm eager loading để trả về response."""
    return db.scalars(_select_task(task_id)).one()


def get_for_update(db: Session, task_id: int) -> Task | None:
    """SELECT ... FOR UPDATE: khóa dòng task tới khi commit/rollback.

    Nếu 2 người cùng assign 1 task cùng lúc, request thứ 2 phải chờ request 1 xong
    -> tránh race condition. (SQLite không hỗ trợ, SQLAlchemy tự bỏ qua mệnh đề này.)
    """
    stmt = (
        select(Task)
        .where(Task.id == task_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return db.scalar(stmt)


def lock_project_status(db: Session, task_id: int) -> ProjectStatus | None:
    """Status của project chứa task, khóa chia sẻ dòng project (giống crud.project.lock_status)
    trong 1 query JOIN, không cần load cả task. None nếu task không tồn tại."""
    stmt = (
        select(Project.status)
        .join(Task, Task.project_id == Project.id)
        .where(Task.id == task_id)
        .with_for_update(read=True, of=Project)
    )
    return db.scalar(stmt)


def exists_by_id(db: Session, task_id: int) -> bool:
    return bool(db.scalar(select(exists().where(Task.id == task_id))))


def _visible_to(viewer_id: int) -> ColumnElement[bool]:
    """Điều kiện: task thuộc project nằm trong workspace mà viewer là thành viên."""
    visible_projects = select(Project.id).where(
        Project.workspace_id.in_(member_workspace_ids(viewer_id))
    )
    return Task.project_id.in_(visible_projects)


def list_tasks(
    db: Session,
    *,
    pagination: PageParams,
    viewer: User,
    include_all: bool = False,
    project_id: int | None = None,
    status: TaskStatus | None = None,
    priority: TaskPriority | None = None,
    assignee_id: int | None = None,
    search: str | None = None,
) -> tuple[list[Task], int]:
    """Lọc + phân trang. Trả về (danh sách task của trang hiện tại, tổng số task khớp filter).

    Chỉ trả task trong workspace `viewer` là thành viên (`include_all` cho admin).
    """
    conditions = [] if include_all else [_visible_to(viewer.id)]
    if project_id is not None:
        conditions.append(Task.project_id == project_id)
    if status is not None:
        conditions.append(Task.status == status)
    if priority is not None:
        conditions.append(Task.priority == priority)
    if assignee_id is not None:
        conditions.append(Task.assignee_id == assignee_id)
    if search:
        # autoescape: ký tự % và _ trong từ khóa được hiểu là ký tự thường
        conditions.append(Task.title.icontains(search, autoescape=True))

    total = db.execute(select(func.count()).select_from(Task).where(*conditions)).scalar_one()
    stmt = (
        select(Task)
        .where(*conditions)
        .options(*TASK_LOAD_OPTIONS)
        .order_by(Task.id.desc())
        .offset(pagination.offset)
        .limit(pagination.limit)
    )
    return list(db.scalars(stmt).all()), total


def create(
    db: Session, *, project: Project, data: TaskCreate, tags: list[Tag], creator: User
) -> Task:
    task = Task(**data.model_dump(exclude={"tag_ids"}), project=project, creator=creator, tags=tags)
    db.add(task)
    activity_crud.add(db, task=task, actor=creator, action=ActivityAction.CREATED)
    db.commit()  # task + activity được lưu trong cùng 1 transaction
    return _reload(db, task.id)


def update(
    db: Session, task: Task, data: TaskUpdate, *, tags: list[Tag] | None, actor: User
) -> Task:
    values = data.model_dump(exclude_unset=True, exclude={"tag_ids"})
    changed = [field for field, value in values.items() if getattr(task, field) != value]
    for field, value in values.items():
        setattr(task, field, value)
    if tags is not None and {t.id for t in task.tags} != {t.id for t in tags}:
        task.tags = tags
        changed.append("tags")

    if changed:
        activity_crud.add(
            db,
            task=task,
            actor=actor,
            action=ActivityAction.UPDATED,
            detail=f"changed: {', '.join(changed)}",
        )
    db.commit()
    return _reload(db, task.id)


def delete(db: Session, task: Task) -> None:
    db.delete(task)
    db.commit()


def assign(db: Session, *, task: Task, assignee: User | None, actor: User) -> Task:
    """Giao task cho user — nghiệp vụ gồm 2 thao tác ghi trong CÙNG 1 transaction:

    1. Cập nhật tasks.assignee_id
    2. Ghi lịch sử vào task_activities

    Chỉ commit 1 lần ở cuối: bước 2 lỗi thì chưa có gì được commit, dependency get_db
    rollback -> không bao giờ có trạng thái "task đã đổi người nhận nhưng không có lịch sử".
    Assign lại đúng người hiện tại thì không ghi gì (giống update khi không có field nào đổi).
    """
    new_assignee_id = assignee.id if assignee else None
    if task.assignee_id != new_assignee_id:
        task.assignee = assignee
        activity_crud.add(
            db,
            task=task,
            actor=actor,
            action=ActivityAction.ASSIGNED,
            detail=f"assigned to {assignee.username}" if assignee else "unassigned",
        )
        db.commit()
    return _reload(db, task.id)


# ---------- Bookmark (Many-to-Many User <-> Task) ----------
def is_bookmarked(db: Session, *, user_id: int, task_id: int) -> bool:
    stmt = select(
        exists().where(task_bookmarks.c.user_id == user_id, task_bookmarks.c.task_id == task_id)
    )
    return bool(db.scalar(stmt))


def add_bookmark(db: Session, *, user_id: int, task_id: int) -> None:
    """Idempotent: bookmark lại task đã bookmark thì không lỗi."""
    if is_bookmarked(db, user_id=user_id, task_id=task_id):
        return
    try:
        db.execute(insert(task_bookmarks).values(user_id=user_id, task_id=task_id))
        db.commit()
    except IntegrityError:
        # 2 request song song cùng insert -> request sau vi phạm khóa chính, coi như đã bookmark
        db.rollback()


def remove_bookmark(db: Session, *, user_id: int, task_id: int) -> None:
    db.execute(
        sql_delete(task_bookmarks).where(
            task_bookmarks.c.user_id == user_id, task_bookmarks.c.task_id == task_id
        )
    )
    db.commit()


def list_bookmarked(
    db: Session, user: User, pagination: PageParams, *, include_all: bool = False
) -> tuple[list[Task], int]:
    """Task user đã bookmark. Bị xóa khỏi workspace thì bookmark vẫn giữ nhưng không hiện ra
    (vào lại workspace thì thấy lại)."""
    conditions = [task_bookmarks.c.user_id == user.id]
    if not include_all:
        conditions.append(_visible_to(user.id))
    total = db.execute(
        select(func.count())
        .select_from(Task)
        .join(task_bookmarks, task_bookmarks.c.task_id == Task.id)
        .where(*conditions)
    ).scalar_one()
    stmt = (
        select(Task)
        .join(task_bookmarks, task_bookmarks.c.task_id == Task.id)
        .where(*conditions)
        .options(*TASK_LOAD_OPTIONS)
        .order_by(task_bookmarks.c.created_at.desc(), Task.id.desc())
        .offset(pagination.offset)
        .limit(pagination.limit)
    )
    return list(db.scalars(stmt).all()), total
