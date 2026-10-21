from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.crud import activity as activity_crud
from app.models import ActivityAction, Comment, Task, User
from app.schemas.comment import CommentCreate, CommentUpdate
from app.schemas.common import PageParams


def list_for_task(
    db: Session, task_id: int, pagination: PageParams
) -> tuple[list[Comment], int]:
    total = db.scalar(select(func.count()).select_from(Comment).where(Comment.task_id == task_id))
    stmt = (
        select(Comment)
        .where(Comment.task_id == task_id)
        .options(joinedload(Comment.author))
        .order_by(Comment.id)
        .offset(pagination.skip)
        .limit(pagination.limit)
    )
    return list(db.scalars(stmt).all()), total


def get(db: Session, *, task_id: int, comment_id: int) -> Comment | None:
    """Lọc theo cả task_id để chặn truy cập chéo: /tasks/1/comments/<id comment của task 2>."""
    stmt = (
        select(Comment)
        .where(Comment.id == comment_id, Comment.task_id == task_id)
        .options(joinedload(Comment.author))
    )
    return db.scalar(stmt)


def create(db: Session, *, task: Task, author: User, data: CommentCreate) -> Comment:
    """Thêm comment + ghi activity trong cùng 1 transaction (1 lần commit duy nhất).

    Lỗi giữa chừng -> chưa commit gì, dependency get_db rollback -> không có comment "mồ côi".
    """
    comment = Comment(task=task, author=author, content=data.content)
    db.add(comment)
    activity_crud.add(db, task=task, actor=author, action=ActivityAction.COMMENTED)
    db.commit()
    db.refresh(comment)
    return comment


def update(db: Session, comment: Comment, data: CommentUpdate) -> Comment:
    comment.content = data.content
    db.commit()
    db.refresh(comment)
    return comment


def delete(db: Session, comment: Comment) -> None:
    db.delete(comment)
    db.commit()
