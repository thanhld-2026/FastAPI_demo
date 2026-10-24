"""Nghiệp vụ của task, nằm giữa router và crud: router chỉ nhận request / trả response."""

from functools import partial

from fastapi import BackgroundTasks
from sqlalchemy.orm import Session

from app import crud, permissions
from app.core import messages
from app.core.exceptions import BadRequestException, NotFoundException
from app.models import Task, TaskPriority, TaskStatus, User
from app.schemas.common import Page, PageParams
from app.schemas.task import TaskOut
from app.services import email as email_service
from app.services import task_cache


def list_project_tasks(
    db: Session,
    project_id: int,
    *,
    pagination: PageParams,
    status: TaskStatus | None,
    priority: TaskPriority | None,
    assignee_id: int | None,
) -> tuple[str, bool]:
    """Danh sách task của 1 project (đã lọc + phân trang), có cache Redis.
    Trả về (chuỗi JSON của response, có lấy từ cache không).

    Gọi SAU khi đã kiểm tra quyền đọc project: cache dùng chung cho mọi thành viên (TaskOut không
    có field riêng của từng người xem), không được làm lộ dữ liệu cho người ngoài.
    Cache sẵn chuỗi JSON: lúc HIT trả thẳng, không phải dựng lại model rồi serialize lần nữa.
    """
    version = task_cache.current_version(project_id)
    key = None
    if version is not None:
        key = task_cache.page_key(
            project_id,
            version,
            status=status,
            priority=priority,
            assignee_id=assignee_id,
            page=pagination.page,
            limit=pagination.limit,
        )
        cached = task_cache.get_page(key)
        if cached is not None:
            return cached, True
    items, total = crud.task.list_tasks(
        db,
        viewer=None,
        project_id=project_id,
        status=status,
        priority=priority,
        assignee_id=assignee_id,
        pagination=pagination,
    )
    page_json = Page[TaskOut].build(items, total, pagination).model_dump_json()
    # Không cache trang rỗng: assignee_id / page tùy ý (vd user không thuộc workspace, trang
    # vượt quá) sẽ tạo vô số key không bao giờ được đọc lại, chiếm bộ nhớ Redis.
    # Trang rỗng thì đọc DB cũng rất rẻ.
    if key is not None and items:
        task_cache.put_page(key, page_json)
    return page_json, False


def assign_task(
    db: Session,
    *,
    task: Task,
    assignee_id: int | None,
    actor: User,
    background_tasks: BackgroundTasks,
) -> Task:
    """Giao task cho 1 thành viên đang hoạt động, role EDITOR trở lên; `None` là bỏ assign.

    Quyền assign (EDITOR) và khóa dòng task đã được dependency AssignableTask xử lý. Role của
    người nhận được đọc kèm khóa FOR SHARE: không bị hạ xuống VIEWER / xóa khỏi workspace giữa
    chừng (xem services/workspaces.py).

    Người MỚI được giao nhận email (chạy ngầm sau khi đã trả response, phụ lục feature 10).
    Không gửi khi: bỏ assign, giao lại đúng người đang làm, hoặc tự giao cho chính mình.
    """
    assignee = None
    if assignee_id is not None:
        assignee = crud.user.get_by_id(db, assignee_id)
        role = crud.workspace.get_role_for_project(db, task.project_id, assignee_id, lock=True)
        if assignee is None or not assignee.is_active or not permissions.can_be_assigned(role):
            raise BadRequestException(messages.ASSIGNEE_NOT_EDITOR)
    notify = None
    if assignee is not None and assignee.id not in (task.assignee_id, actor.id):
        # Lấy dữ liệu thuần TRƯỚC khi commit (sau commit các object bị expire, đọc lại tốn query);
        # background task chỉ nhận dữ liệu thuần vì lúc chạy session của request đã đóng
        notify = partial(
            email_service.notify_task_assigned,
            assignee.email,
            task_id=task.id,
            task_title=task.title,
            project_name=task.project.name,
            priority=task.priority.value,
            due_date=task.due_date.isoformat() if task.due_date else None,
            assigner=actor.full_name,
        )
    updated = crud.task.assign(db, task=task, assignee=assignee, actor=actor)
    if notify is not None:  # chỉ tới đây khi assign đã commit thành công
        background_tasks.add_task(notify)
    return updated


def set_task_label(
    db: Session, *, task: Task, label_id: int, attached: bool, actor: User
) -> Task:
    """Label trên URL phải thuộc đúng project của task, nếu không coi như không tồn tại (404).
    Khóa chia sẻ label trước (không bị xóa giữa chừng), sau đó crud khóa task."""
    label = crud.label.get_in_project(db, task.project_id, label_id, for_share=True)
    if label is None:
        raise NotFoundException(messages.LABEL_NOT_FOUND)
    return crud.task.set_label(db, task=task, label=label, attached=attached, actor=actor)
