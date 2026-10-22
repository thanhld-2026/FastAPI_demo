from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import WORKSPACE_NAME_MAX_LENGTH
from app.database import Base
from app.models.base import TimestampMixin, UTCDateTime, enum_column
from app.models.enums import WorkspaceRole

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.user import User


class Workspace(TimestampMixin, Base):
    """Không gian làm việc của 1 nhóm: chứa project, quyền của user đi theo membership."""

    __tablename__ = "workspaces"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(WORKSPACE_NAME_MAX_LENGTH))
    # RESTRICT: không xóa được user đang sở hữu workspace (phải xóa / chuyển workspace trước)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)

    owner: Mapped[User] = relationship()
    members: Mapped[list[WorkspaceMember]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan", order_by="WorkspaceMember.user_id"
    )
    projects: Mapped[list[Project]] = relationship(back_populates="workspace")


class WorkspaceMember(Base):
    """Bảng trung gian User <-> Workspace có thêm cột `role`.

    Khác task_tags / task_bookmarks (bảng thuần, dùng `secondary=`): bảng có dữ liệu riêng thì
    khai báo thành class (association object) để đọc / ghi được cột role.
    """

    __tablename__ = "workspace_members"

    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    role: Mapped[WorkspaceRole] = mapped_column(enum_column(WorkspaceRole))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), server_default=func.now())

    workspace: Mapped[Workspace] = relationship(back_populates="members")
    user: Mapped[User] = relationship()
