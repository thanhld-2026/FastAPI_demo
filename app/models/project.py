from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import PROJECT_NAME_MAX_LENGTH
from app.database import Base
from app.models.base import TimestampMixin

if TYPE_CHECKING:
    from app.models.task import Task
    from app.models.user import User


class Project(TimestampMixin, Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(PROJECT_NAME_MAX_LENGTH), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    # Người tạo project = Project Manager (PM) của project đó
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)

    owner: Mapped[User] = relationship(back_populates="owned_projects")
    # cascade="all, delete-orphan": xóa project -> xóa luôn các task thuộc project
    tasks: Mapped[list[Task]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="Task.id"
    )
