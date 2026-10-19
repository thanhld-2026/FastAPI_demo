from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Task, User


def get_by_id(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def get_profile(db: Session, username: str) -> User | None:
    """User kèm project đang quản lý + task được giao, load sẵn trong 3 query cố định."""
    stmt = (
        select(User)
        .where(User.username == username)
        .options(
            selectinload(User.owned_projects),
            selectinload(User.assigned_tasks).joinedload(Task.assignee),
        )
    )
    return db.scalar(stmt)
