from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import TAG_NAME_MAX_LENGTH
from app.database import Base
from app.models.associations import task_tags

if TYPE_CHECKING:
    from app.models.task import Task


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(TAG_NAME_MAX_LENGTH), unique=True, index=True)

    tasks: Mapped[list[Task]] = relationship(secondary=task_tags, back_populates="tags")
