from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import LABEL_COLOR_LENGTH, LABEL_NAME_MAX_LENGTH
from app.database import Base
from app.models.associations import task_labels

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.task import Task


class Label(Base):
    """Nhãn của 1 project (mỗi project có bộ label riêng, khác tag dùng chung toàn hệ thống)."""

    __tablename__ = "labels"
    # Tên label không trùng trong cùng 1 project (2 project khác nhau có thể cùng có "bug")
    __table_args__ = (UniqueConstraint("project_id", "name", name="uq_labels_project_id_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(LABEL_NAME_MAX_LENGTH))
    color: Mapped[str] = mapped_column(String(LABEL_COLOR_LENGTH))

    project: Mapped[Project] = relationship(back_populates="labels")
    tasks: Mapped[list[Task]] = relationship(secondary=task_labels, back_populates="labels")
