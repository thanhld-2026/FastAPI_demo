from fastapi import APIRouter, BackgroundTasks, status

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
from app.services import email as email_service

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
    summary="Thêm comment (gửi email thông báo chạy ngầm)",
    responses=error_responses(401, 403, 404),
)
def create_comment(
    data: CommentCreate,
    task: TaskDep,
    current_user: CurrentUser,
    db: DbSession,
    background_tasks: BackgroundTasks,
):
    # Người nhận: người tạo task + người được assign (trừ chính người comment).
    # Lấy dữ liệu thuần TRƯỚC khi commit (sau commit các object bị expire).
    recipients = sorted(
        {
            user.email
            for user in (task.creator, task.assignee)
            if user is not None and user.id != current_user.id and user.is_active
        }
    )
    task_id, task_title, commenter = task.id, task.title, current_user.username

    comment = crud.comment.create(db, task=task, author=current_user, data=data)

    if recipients:
        # add_task chỉ đăng ký việc cần làm; FastAPI chạy nó SAU KHI đã trả response
        # -> client không phải chờ gửi mail (có thể mất vài giây).
        background_tasks.add_task(
            email_service.notify_new_comment,
            recipients,
            task_id=task_id,
            task_title=task_title,
            commenter=commenter,
            content=data.content,
        )
    return comment


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
