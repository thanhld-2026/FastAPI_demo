from fastapi import APIRouter, status

from app import crud
from app.core.responses import error_responses
from app.dependencies import (
    CurrentUser,
    DbSession,
    ExistingTaskId,
    ModifiableComment,
    Pagination,
    TaskDep,
)
from app.schemas.comment import CommentCreate, CommentOut, CommentUpdate
from app.schemas.common import Page

router = APIRouter(prefix="/api/tasks/{task_id}/comments", tags=["Comments"])


@router.get(
    "",
    response_model=Page[CommentOut],
    summary="Danh sách comment của task",
    responses=error_responses(404),
)
def list_comments(task_id: ExistingTaskId, db: DbSession, pagination: Pagination):
    items, total = crud.comment.list_for_task(
        db, task_id, skip=pagination.skip, limit=pagination.limit
    )
    return Page.build(items, total, pagination)


@router.post(
    "",
    response_model=CommentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Thêm comment (cần đăng nhập)",
    responses=error_responses(401, 403, 404),
)
def create_comment(data: CommentCreate, task: TaskDep, current_user: CurrentUser, db: DbSession):
    return crud.comment.create(db, task=task, author=current_user, data=data)


@router.put(
    "/{comment_id}",
    response_model=CommentOut,
    summary="Sửa comment (tác giả / PM / Admin)",
    responses=error_responses(401, 403, 404),
)
def update_comment(data: CommentUpdate, comment: ModifiableComment, db: DbSession):
    return crud.comment.update(db, comment, data)


@router.delete(
    "/{comment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Xóa comment (tác giả / PM / Admin)",
    responses=error_responses(401, 403, 404),
)
def delete_comment(comment: ModifiableComment, db: DbSession):
    crud.comment.delete(db, comment)
