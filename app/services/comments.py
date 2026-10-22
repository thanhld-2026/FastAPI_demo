"""Nghiệp vụ của comment: lưu comment + báo email (chạy ngầm) cho người liên quan tới task."""

from fastapi import BackgroundTasks
from sqlalchemy.orm import Session

from app import crud
from app.models import Comment, Task, User
from app.schemas.comment import CommentCreate
from app.services import email as email_service


def _notification_recipients(db: Session, task: Task, commenter: User) -> list[str]:
    """Người tạo task + người được assign, trừ chính người comment, user đã bị khóa và người
    không còn trong workspace (đã rời thì không được đọc nội dung task nữa)."""
    candidates = {
        user
        for user in (task.creator, task.assignee)
        if user is not None and user.id != commenter.id and user.is_active
    }
    if not candidates:
        return []
    members = crud.workspace.member_user_ids(
        db, task.project.workspace_id, {user.id for user in candidates}
    )
    return sorted(user.email for user in candidates if user.id in members)


def create_comment(
    db: Session,
    *,
    task: Task,
    author: User,
    data: CommentCreate,
    background_tasks: BackgroundTasks,
) -> Comment:
    # Lấy dữ liệu thuần TRƯỚC khi commit (sau commit các object bị expire)
    recipients = _notification_recipients(db, task, author)
    task_id, task_title, commenter = task.id, task.title, author.full_name

    comment = crud.comment.create(db, task=task, author=author, data=data)

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
