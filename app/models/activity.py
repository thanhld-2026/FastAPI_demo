from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import ACTIVITY_DETAIL_MAX_LENGTH
from app.database import Base
from app.models.base import enum_column
from app.models.enums import ActivityAction

if TYPE_CHECKING:
    from app.models.task import Task
    from app.models.user import User


class TaskActivity(Base):
    """Lịch sử hoạt động của task (ai làm gì, lúc nào).

    Được ghi CÙNG transaction với thao tác chính (assign, comment, ...): nếu ghi log
    thất bại thì thao tác chính cũng bị rollback -> dữ liệu luôn nhất quán.
    """

    __tablename__ = "task_activities"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    # RESTRICT: lịch sử là dữ liệu audit, không được mất theo khi xóa user
    # (muốn "xóa" user thì khóa tài khoản: is_active = False)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    action: Mapped[ActivityAction] = mapped_column(enum_column(ActivityAction))
    detail: Mapped[str | None] = mapped_column(String(ACTIVITY_DETAIL_MAX_LENGTH))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    task: Mapped[Task] = relationship(back_populates="activities")
    actor: Mapped[User] = relationship()
