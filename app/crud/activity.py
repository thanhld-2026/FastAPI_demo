from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models import ActivityAction, Task, TaskActivity, User
from app.schemas.common import PageParams


def add(
    db: Session, *, task: Task, actor: User, action: ActivityAction, detail: str | None = None
) -> TaskActivity:
    """Ghi 1 dòng activity vào session.

    Cố ý KHÔNG commit: hàm gọi (assign, comment, ...) sẽ commit 1 lần duy nhất
    để thao tác chính và activity nằm trong cùng 1 transaction.
    """
    activity = TaskActivity(task=task, actor=actor, action=action, detail=detail)
    db.add(activity)
    return activity


def list_for_task(
    db: Session, task_id: int, pagination: PageParams
) -> tuple[list[TaskActivity], int]:
    total = db.scalar(
        select(func.count()).select_from(TaskActivity).where(TaskActivity.task_id == task_id)
    )
    stmt = (
        select(TaskActivity)
        .where(TaskActivity.task_id == task_id)
        .options(joinedload(TaskActivity.actor))
        .order_by(TaskActivity.id)
        .offset(pagination.skip)
        .limit(pagination.limit)
    )
    return list(db.scalars(stmt).all()), total
