from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String, Text, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import (
    EMAIL_MAX_LENGTH,
    FULL_NAME_MAX_LENGTH,
    PASSWORD_HASH_MAX_LENGTH,
    USERNAME_MAX_LENGTH,
)
from app.database import Base
from app.models.associations import task_bookmarks
from app.models.base import TimestampMixin, enum_column
from app.models.enums import UserRole

if TYPE_CHECKING:
    from app.models.comment import Comment
    from app.models.project import Project
    from app.models.task import Task


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(USERNAME_MAX_LENGTH), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(EMAIL_MAX_LENGTH), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(PASSWORD_HASH_MAX_LENGTH))
    full_name: Mapped[str | None] = mapped_column(String(FULL_NAME_MAX_LENGTH))
    bio: Mapped[str | None] = mapped_column(Text)
    role: Mapped[UserRole] = mapped_column(
        enum_column(UserRole), default=UserRole.MEMBER, server_default=UserRole.MEMBER.value
    )
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())

    # One-to-Many: các project do user tạo
    created_projects: Mapped[list[Project]] = relationship(
        back_populates="creator", order_by="Project.id"
    )
    # Task có 2 khóa ngoại tới users -> phải chỉ rõ foreign_keys cho từng relationship
    created_tasks: Mapped[list[Task]] = relationship(
        back_populates="creator", foreign_keys="Task.creator_id"
    )
    assigned_tasks: Mapped[list[Task]] = relationship(
        back_populates="assignee", foreign_keys="Task.assignee_id", order_by="Task.id"
    )
    comments: Mapped[list[Comment]] = relationship(back_populates="author")
    # Many-to-Many qua bảng trung gian task_bookmarks
    bookmarked_tasks: Mapped[list[Task]] = relationship(
        secondary=task_bookmarks, back_populates="bookmarked_by"
    )
