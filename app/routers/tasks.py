from typing import Annotated

from fastapi import APIRouter, Query, status
from pydantic import PositiveInt

from app import crud
from app.core.constants import TASK_SEARCH_MAX_LENGTH
from app.core.responses import error_responses
from app.dependencies import (
    CurrentUser,
    DbSession,
    DeletableTask,
    EditableTask,
    ExistingTaskId,
    Pagination,
    TaskDep,
    get_tags_by_ids,
)
from app.models import TaskPriority, TaskStatus
from app.schemas.common import Page
from app.schemas.task import BookmarkOut, TaskOut, TaskUpdate

router = APIRouter(prefix="/api/tasks", tags=["Tasks"])


@router.get("", response_model=Page[TaskOut], summary="Tìm kiếm / lọc / phân trang task")
def list_tasks(
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
        status=task_status,
        priority=priority,
        project_id=project_id,
        assignee_id=assignee_id,
        search=q,
        skip=pagination.skip,
        limit=pagination.limit,
    )
    return Page.build(items, total, pagination)


@router.get(
    "/{task_id}", response_model=TaskOut, summary="Chi tiết task", responses=error_responses(404)
)
def get_task(task: TaskDep):
    return task


@router.put(
    "/{task_id}",
    response_model=TaskOut,
    summary="Cập nhật task (người tạo / người được assign / PM / Admin)",
    responses=error_responses(400, 401, 403, 404),
)
def update_task(data: TaskUpdate, task: EditableTask, db: DbSession):
    tags = get_tags_by_ids(db, data.tag_ids) if data.tag_ids is not None else None
    return crud.task.update(db, task, data, tags=tags)


@router.delete(
    "/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Xóa task (người tạo / PM / Admin)",
    responses=error_responses(401, 403, 404),
)
def delete_task(task: DeletableTask, db: DbSession):
    crud.task.delete(db, task)


@router.post(
    "/{task_id}/bookmark",
    response_model=BookmarkOut,
    summary="Bookmark task (cần đăng nhập)",
    responses=error_responses(401, 403, 404),
)
def bookmark_task(task_id: ExistingTaskId, current_user: CurrentUser, db: DbSession):
    crud.task.add_bookmark(db, user_id=current_user.id, task_id=task_id)
    return BookmarkOut(task_id=task_id, bookmarked=True)


@router.delete(
    "/{task_id}/bookmark",
    response_model=BookmarkOut,
    summary="Bỏ bookmark task (idempotent)",
    responses=error_responses(401, 403, 404),
)
def unbookmark_task(task_id: ExistingTaskId, current_user: CurrentUser, db: DbSession):
    """Cố ý idempotent, giống POST /bookmark: gọi lại nhiều lần hoặc task chưa từng được
    bookmark vẫn trả 200 `bookmarked: false`, vì trạng thái cuối cùng là như nhau."""
    crud.task.remove_bookmark(db, user_id=current_user.id, task_id=task_id)
    return BookmarkOut(task_id=task_id, bookmarked=False)
