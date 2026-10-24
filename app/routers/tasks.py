from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Query, status
from pydantic import PositiveInt

from app import crud
from app.core.constants import TASK_SEARCH_MAX_LENGTH
from app.core.responses import error_responses
from app.dependencies import (
    AssignableTask,
    CurrentUser,
    DbSession,
    DeletableTask,
    EditableTask,
    Pagination,
    ReadableTask,
    ReadableTaskId,
    get_labels_by_ids,
)
from app.models import TaskPriority, TaskStatus
from app.schemas.common import Page
from app.schemas.task import ActivityOut, BookmarkOut, TaskAssign, TaskOut, TaskUpdate
from app.services import tasks as task_service

router = APIRouter(prefix="/tasks", tags=["Tasks"])


@router.get(
    "",
    response_model=Page[TaskOut],
    summary="Tìm kiếm / lọc / phân trang task (trong các workspace tôi là thành viên)",
    responses=error_responses(401, 403),
)
def list_tasks(
    current_user: CurrentUser,
    db: DbSession,
    pagination: Pagination,
    task_status: Annotated[TaskStatus | None, Query(alias="status")] = None,
    priority: TaskPriority | None = None,
    project_id: PositiveInt | None = None,
    assignee_id: PositiveInt | None = None,
    q: Annotated[
        str | None,
        Query(min_length=1, max_length=TASK_SEARCH_MAX_LENGTH, description="Tìm theo tiêu đề"),
    ] = None,
):
    items, total = crud.task.list_tasks(
        db,
        viewer=current_user,
        status=task_status,
        priority=priority,
        project_id=project_id,
        assignee_id=assignee_id,
        search=q,
        pagination=pagination,
    )
    return Page.build(items, total, pagination)


@router.get(
    "/{task_id}",
    response_model=TaskOut,
    summary="Chi tiết task",
    responses=error_responses(401, 403, 404),
)
def get_task(task: ReadableTask):
    return task


@router.put(
    "/{task_id}",
    response_model=TaskOut,
    summary="[EDITOR] Cập nhật task",
    responses=error_responses(400, 401, 403, 404, 409),
)
def update_task(data: TaskUpdate, task: EditableTask, current_user: CurrentUser, db: DbSession):
    labels = None
    if data.label_ids is not None:
        labels = get_labels_by_ids(db, task.project_id, data.label_ids)
    return crud.task.update(db, task, data, labels=labels, actor=current_user)


@router.delete(
    "/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="[EDITOR] Xóa task mình tạo, OWNER xóa được mọi task",
    responses=error_responses(401, 403, 404, 409),
)
def delete_task(task: DeletableTask, db: DbSession):
    crud.task.delete(db, task)


@router.post(
    "/{task_id}/assign",
    response_model=TaskOut,
    summary="[EDITOR] Giao task cho thành viên (role EDITOR trở lên)",
    responses=error_responses(400, 401, 403, 404, 409),
)
def assign_task(
    data: TaskAssign,
    task: AssignableTask,
    current_user: CurrentUser,
    db: DbSession,
    background_tasks: BackgroundTasks,
):
    """Người mới được giao nhận email thông báo (gửi ngầm sau khi trả response)."""
    return task_service.assign_task(
        db,
        task=task,
        assignee_id=data.assignee_id,
        actor=current_user,
        background_tasks=background_tasks,
    )


@router.post(
    "/{task_id}/labels/{label_id}",
    response_model=TaskOut,
    summary="[EDITOR] Gắn label (cùng project) cho task (idempotent)",
    responses=error_responses(401, 403, 404, 409),
)
def add_task_label(
    label_id: int, task: EditableTask, current_user: CurrentUser, db: DbSession
):
    return task_service.set_task_label(
        db, task=task, label_id=label_id, attached=True, actor=current_user
    )


@router.delete(
    "/{task_id}/labels/{label_id}",
    response_model=TaskOut,
    summary="[EDITOR] Gỡ label khỏi task (idempotent)",
    responses=error_responses(401, 403, 404, 409),
)
def remove_task_label(
    label_id: int, task: EditableTask, current_user: CurrentUser, db: DbSession
):
    return task_service.set_task_label(
        db, task=task, label_id=label_id, attached=False, actor=current_user
    )


@router.post(
    "/{task_id}/bookmark",
    response_model=BookmarkOut,
    summary="Bookmark task (thành viên workspace)",
    responses=error_responses(401, 403, 404),
)
def bookmark_task(current_user: CurrentUser, task_id: ReadableTaskId, db: DbSession):
    """Được cả khi project đã archive: bookmark là dữ liệu cá nhân, không sửa gì trong project."""
    crud.task.add_bookmark(db, user_id=current_user.id, task_id=task_id)
    return BookmarkOut(task_id=task_id, bookmarked=True)


@router.delete(
    "/{task_id}/bookmark",
    response_model=BookmarkOut,
    summary="Bỏ bookmark task (idempotent)",
    responses=error_responses(401, 403, 404),
)
def unbookmark_task(current_user: CurrentUser, task_id: ReadableTaskId, db: DbSession):
    """Cố ý idempotent, giống POST /bookmark: gọi lại nhiều lần hoặc task chưa từng được
    bookmark vẫn trả 200 `bookmarked: false`, vì trạng thái cuối cùng là như nhau."""
    crud.task.remove_bookmark(db, user_id=current_user.id, task_id=task_id)
    return BookmarkOut(task_id=task_id, bookmarked=False)


@router.get(
    "/{task_id}/activities",
    response_model=Page[ActivityOut],
    summary="Lịch sử hoạt động của task",
    responses=error_responses(401, 403, 404),
)
def list_activities(task_id: ReadableTaskId, db: DbSession, pagination: Pagination):
    items, total = crud.activity.list_for_task(db, task_id, pagination)
    return Page.build(items, total, pagination)
