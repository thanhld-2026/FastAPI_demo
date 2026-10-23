from fastapi import APIRouter, BackgroundTasks, status

from app import crud
from app.core.responses import error_responses
from app.dependencies import (
    CurrentUser,
    DbSession,
    EditableTask,
    ModifiableComment,
    Pagination,
    ReadableTaskId,
)
from app.schemas.comment import CommentCreate, CommentOut, CommentUpdate
from app.schemas.common import Page
from app.services import comments as comment_service

router = APIRouter(prefix="/tasks/{task_id}/comments", tags=["Comments"])


@router.get(
    "",
    response_model=Page[CommentOut],
    summary="Danh sách comment của task",
    responses=error_responses(401, 403, 404),
)
def list_comments(task_id: ReadableTaskId, db: DbSession, pagination: Pagination):
    items, total = crud.comment.list_for_task(db, task_id, pagination)
    return Page.build(items, total, pagination)


@router.post(
    "",
    response_model=CommentOut,
    status_code=status.HTTP_201_CREATED,
    summary="[EDITOR] Thêm comment (gửi email thông báo chạy ngầm)",
    responses=error_responses(401, 403, 404, 409),
)
def create_comment(
    data: CommentCreate,
    current_user: CurrentUser,
    task: EditableTask,
    db: DbSession,
    background_tasks: BackgroundTasks,
):
    return comment_service.create_comment(
        db, task=task, author=current_user, data=data, background_tasks=background_tasks
    )


@router.put(
    "/{comment_id}",
    response_model=CommentOut,
    summary="Sửa comment (tác giả / OWNER)",
    responses=error_responses(401, 403, 404, 409),
)
def update_comment(data: CommentUpdate, comment: ModifiableComment, db: DbSession):
    return crud.comment.update(db, comment, data)


@router.delete(
    "/{comment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Xóa comment (tác giả / OWNER)",
    responses=error_responses(401, 403, 404, 409),
)
def delete_comment(comment: ModifiableComment, db: DbSession):
    crud.comment.delete(db, comment)
