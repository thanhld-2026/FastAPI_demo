from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String, func, text
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
    # passive_deletes="all": ORM không tự load / sửa project khi xóa workspace, để FK RESTRICT
    # trong DB quyết định (không thì ORM thử set workspace_id = NULL cho project còn sót)
    projects: Mapped[list[Project]] = relationship(
        back_populates="workspace", passive_deletes="all"
    )


class WorkspaceMember(Base):
    """Bảng trung gian User <-> Workspace có thêm cột `role`.

    Khác task_labels / task_bookmarks (bảng thuần, dùng `secondary=`): bảng có dữ liệu riêng thì
    khai báo thành class (association object) để đọc / ghi được cột role.
    """

    __tablename__ = "workspace_members"
    # Owner được lưu ở 2 nơi: workspaces.owner_id (hiển thị, FK RESTRICT chặn xóa user đang sở
    # hữu workspace) và dòng membership role OWNER (phân quyền). Partial unique index: DB chặn
    # 2 dòng OWNER trong cùng 1 workspace. 2 nơi chỉ được ghi cùng nhau trong 1 transaction:
    # crud.workspace.create và services/workspaces.transfer_ownership.
    __table_args__ = (
        Index(
            "uq_workspace_members_one_owner",
            "workspace_id",
            unique=True,
            postgresql_where=text("role = 'OWNER'"),
            sqlite_where=text("role = 'OWNER'"),
        ),
    )

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
