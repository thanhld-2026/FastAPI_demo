from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import TASK_TITLE_MAX_LENGTH
from app.database import Base
from app.models.associations import task_bookmarks, task_tags
from app.models.base import TimestampMixin, enum_column
from app.models.enums import TaskPriority, TaskStatus

if TYPE_CHECKING:
    from app.models.comment import Comment
    from app.models.project import Project
    from app.models.tag import Tag
    from app.models.user import User


class Task(TimestampMixin, Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(TASK_TITLE_MAX_LENGTH))
    description: Mapped[str | None] = mapped_column(Text)
    # index cho các cột hay dùng để lọc (?status=...&priority=...)
    status: Mapped[TaskStatus] = mapped_column(
        enum_column(TaskStatus),
        default=TaskStatus.TODO,
        server_default=TaskStatus.TODO.value,
        index=True,
    )
    priority: Mapped[TaskPriority] = mapped_column(
        enum_column(TaskPriority),
        default=TaskPriority.MEDIUM,
        server_default=TaskPriority.MEDIUM.value,
        index=True,
    )
    due_date: Mapped[date | None] = mapped_column(Date)

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    creator_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    # Xóa user được assign -> task chuyển về trạng thái chưa assign
    assignee_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )

    # Many-to-One
    project: Mapped[Project] = relationship(back_populates="tasks")
    creator: Mapped[User] = relationship(foreign_keys=[creator_id], back_populates="created_tasks")
    assignee: Mapped[User | None] = relationship(
        foreign_keys=[assignee_id], back_populates="assigned_tasks"
    )
    # Many-to-Many
    tags: Mapped[list[Tag]] = relationship(
        secondary=task_tags, back_populates="tasks", order_by="Tag.name"
    )
    bookmarked_by: Mapped[list[User]] = relationship(
        secondary=task_bookmarks, back_populates="bookmarked_tasks"
    )
    # One-to-Many
    comments: Mapped[list[Comment]] = relationship(
        back_populates="task", cascade="all, delete-orphan", order_by="Comment.id"
    )
