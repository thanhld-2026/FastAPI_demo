"""Nghiệp vụ của task, nằm giữa router và crud: router chỉ nhận request / trả response."""

from sqlalchemy.orm import Session

from app import crud
from app.core import messages
from app.core.exceptions import BadRequestException
from app.models import Task, User


def assign_task(db: Session, *, task: Task, assignee_id: int | None, actor: User) -> Task:
    """Giao task cho 1 user đang hoạt động; `assignee_id=None` là bỏ assign.

    Quyền assign (PM / admin) và khóa dòng task đã được dependency get_task_for_assign xử lý.
    """
    assignee = None
    if assignee_id is not None:
        assignee = crud.user.get_by_id(db, assignee_id)
        if assignee is None or not assignee.is_active:
            raise BadRequestException(messages.ASSIGNEE_NOT_FOUND)
    return crud.task.assign(db, task=task, assignee=assignee, actor=actor)
