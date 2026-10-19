from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models import Project, Tag, Task, User
from app.schemas.task import TaskCreate

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


def list_for_project(db: Session, project_id: int) -> list[Task]:
    stmt = (
        select(Task)
        .where(Task.project_id == project_id)
        .options(*TASK_LOAD_OPTIONS)
        .order_by(Task.id.desc())
    )
    return list(db.scalars(stmt).all())


def create(
    db: Session, *, project: Project, data: TaskCreate, tags: list[Tag], creator: User
) -> Task:
    task = Task(**data.model_dump(exclude={"tag_ids"}), project=project, creator=creator, tags=tags)
    db.add(task)
    db.commit()
    return get(db, task.id)
