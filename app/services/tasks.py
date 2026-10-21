"""Nghiệp vụ của task, nằm giữa router và crud: router chỉ nhận request / trả response."""

from sqlalchemy.orm import Session

from app import crud, permissions
from app.core import messages
from app.core.exceptions import BadRequestException, NotFoundException
from app.models import Task, User


def assign_task(db: Session, *, task: Task, assignee_id: int | None, actor: User) -> Task:
    """Giao task cho 1 thành viên đang hoạt động, role EDITOR trở lên; `None` là bỏ assign.

    Quyền assign (EDITOR) và khóa dòng task đã được dependency get_task_for_assign xử lý.
    """
    assignee = None
    if assignee_id is not None:
        assignee = crud.user.get_by_id(db, assignee_id)
        role = crud.workspace.get_role_for_project(db, task.project_id, assignee_id)
        if assignee is None or not assignee.is_active or not permissions.can_be_assigned(role):
            raise BadRequestException(messages.ASSIGNEE_NOT_EDITOR)
    return crud.task.assign(db, task=task, assignee=assignee, actor=actor)


def set_task_label(
    db: Session, *, task: Task, label_id: int, attached: bool, actor: User
) -> Task:
    """Label trên URL phải thuộc đúng project của task, nếu không coi như không tồn tại (404)."""
    label = crud.label.get(db, label_id)
    if label is None or label.project_id != task.project_id:
        raise NotFoundException(messages.LABEL_NOT_FOUND)
    return crud.task.set_label(db, task=task, label=label, attached=attached, actor=actor)
