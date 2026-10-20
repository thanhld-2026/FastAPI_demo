from sqlalchemy import delete as sql_delete
from sqlalchemy import exists, func, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from app.crud import activity as activity_crud
from app.models import (
    ActivityAction,
    Project,
    Tag,
    Task,
    TaskPriority,
    TaskStatus,
    User,
    task_bookmarks,
)
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


def get(db: Session, task_id: int) -> Task | None:
    stmt = select(Task).where(Task.id == task_id).options(*TASK_LOAD_OPTIONS)
    return db.scalar(stmt)


def get_for_update(db: Session, task_id: int) -> Task | None:
    """SELECT ... FOR UPDATE: khóa dòng task tới khi commit/rollback.

    Nếu 2 PM cùng assign 1 task cùng lúc, request thứ 2 phải chờ request 1 xong
    -> tránh race condition. (SQLite không hỗ trợ, SQLAlchemy tự bỏ qua mệnh đề này.)
    """
    stmt = (
        select(Task)
        .where(Task.id == task_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return db.scalar(stmt)


def exists_by_id(db: Session, task_id: int) -> bool:
    return bool(db.scalar(select(exists().where(Task.id == task_id))))


def list_tasks(
    db: Session,
    *,
    skip: int,
    limit: int,
    project_id: int | None = None,
    status: TaskStatus | None = None,
    priority: TaskPriority | None = None,
    assignee_id: int | None = None,
    search: str | None = None,
) -> tuple[list[Task], int]:
    """Lọc + phân trang. Trả về (danh sách task của trang hiện tại, tổng số task khớp filter)."""
    conditions = []
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

    total = db.scalar(select(func.count()).select_from(Task).where(*conditions))
    stmt = (
        select(Task)
        .where(*conditions)
        .options(*TASK_LOAD_OPTIONS)
        .order_by(Task.id.desc())
        .offset(skip)
        .limit(limit)
    )
    return list(db.scalars(stmt).all()), total


def create(
    db: Session, *, project: Project, data: TaskCreate, tags: list[Tag], creator: User
) -> Task:
    task = Task(**data.model_dump(exclude={"tag_ids"}), project=project, creator=creator, tags=tags)
    db.add(task)
    activity_crud.add(db, task=task, actor=creator, action=ActivityAction.CREATED)
    db.commit()  # task + activity được lưu trong cùng 1 transaction
    return get(db, task.id)


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
    return get(db, task.id)


def delete(db: Session, task: Task) -> None:
    db.delete(task)
    db.commit()


def assign(db: Session, *, task: Task, assignee: User | None, actor: User) -> Task:
    """Giao task cho user — nghiệp vụ gồm 2 thao tác ghi trong CÙNG 1 transaction:

    1. Cập nhật tasks.assignee_id
    2. Ghi lịch sử vào task_activities

    Nếu bước 2 lỗi -> rollback cả bước 1, không bao giờ có trạng thái
    "task đã đổi người nhận nhưng không có lịch sử".
    """
    try:
        task.assignee = assignee
        activity_crud.add(
            db,
            task=task,
            actor=actor,
            action=ActivityAction.ASSIGNED,
            detail=f"assigned to {assignee.username}" if assignee else "unassigned",
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return get(db, task.id)


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
    db: Session, user_id: int, *, skip: int, limit: int
) -> tuple[list[Task], int]:
    total = db.scalar(
        select(func.count()).select_from(task_bookmarks).where(task_bookmarks.c.user_id == user_id)
    )
    stmt = (
        select(Task)
        .join(task_bookmarks, task_bookmarks.c.task_id == Task.id)
        .where(task_bookmarks.c.user_id == user_id)
        .options(*TASK_LOAD_OPTIONS)
        .order_by(task_bookmarks.c.created_at.desc(), Task.id.desc())
        .offset(skip)
        .limit(limit)
    )
    return list(db.scalars(stmt).all()), total
