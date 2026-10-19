from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app import crud, permissions
from app.dependencies import CurrentUser, DbSession, TaskDep, load_tags_or_400
from app.models import TaskPriority, TaskStatus
from app.schemas.common import Page
from app.schemas.task import BookmarkOut, TaskOut, TaskUpdate

router = APIRouter(prefix="/api/tasks", tags=["Tasks"])


@router.get("", response_model=Page[TaskOut], summary="Tìm kiếm / lọc / phân trang task")
def list_tasks(
    db: DbSession,
    task_status: Annotated[TaskStatus | None, Query(alias="status")] = None,
    priority: TaskPriority | None = None,
    project_id: int | None = None,
    assignee_id: int | None = None,
    q: Annotated[str | None, Query(min_length=1, max_length=100, description="Tìm theo tiêu đề")] = None,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    items, total = crud.task.list_tasks(
        db,
        status=task_status,
        priority=priority,
        project_id=project_id,
        assignee_id=assignee_id,
        search=q,
        skip=skip,
        limit=limit,
    )
    return {"items": items, "total": total, "skip": skip, "limit": limit}


@router.get("/{task_id}", response_model=TaskOut, summary="Chi tiết task")
def get_task(task: TaskDep):
    return task


@router.put(
    "/{task_id}",
    response_model=TaskOut,
    summary="Cập nhật task (người tạo / người được assign / PM / Admin)",
)
def update_task(data: TaskUpdate, task: TaskDep, current_user: CurrentUser, db: DbSession):
    if not permissions.can_edit_task(current_user, task):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Not allowed to edit this task")
    tags = load_tags_or_400(db, data.tag_ids) if data.tag_ids is not None else None
    return crud.task.update(db, task, data, tags=tags)


@router.delete(
    "/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Xóa task (người tạo / PM / Admin)",
)
def delete_task(task: TaskDep, current_user: CurrentUser, db: DbSession):
    if not permissions.can_delete_task(current_user, task):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Not allowed to delete this task")
    crud.task.delete(db, task)


@router.post(
    "/{task_id}/bookmark", response_model=BookmarkOut, summary="Bookmark task (cần đăng nhập)"
)
def bookmark_task(task_id: int, current_user: CurrentUser, db: DbSession):
    if not crud.task.exists_by_id(db, task_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Task not found")
    crud.task.add_bookmark(db, user_id=current_user.id, task_id=task_id)
    return BookmarkOut(task_id=task_id, bookmarked=True)


@router.delete("/{task_id}/bookmark", response_model=BookmarkOut, summary="Bỏ bookmark task")
def unbookmark_task(task_id: int, current_user: CurrentUser, db: DbSession):
    if not crud.task.exists_by_id(db, task_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Task not found")
    crud.task.remove_bookmark(db, user_id=current_user.id, task_id=task_id)
    return BookmarkOut(task_id=task_id, bookmarked=False)
