from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import PROJECT_NAME_MAX_LENGTH
from app.database import Base
from app.models.base import TimestampMixin, enum_column
from app.models.enums import ProjectStatus

if TYPE_CHECKING:
    from app.models.task import Task
    from app.models.user import User
    from app.models.workspace import Workspace


class Project(TimestampMixin, Base):
    __tablename__ = "projects"
    # GET /projects?status=... lọc theo status rồi ORDER BY id: index ghép (status, id) cho DB đọc
    # thẳng các dòng đúng status theo thứ tự id. Index đơn trên status (chỉ 2 giá trị) gần như
    # không được dùng: 1 giá trị chiếm phần lớn bảng thì quét bảng còn nhanh hơn.
    __table_args__ = (Index("ix_projects_status_id", "status", "id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(PROJECT_NAME_MAX_LENGTH), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ProjectStatus] = mapped_column(
        enum_column(ProjectStatus),
        default=ProjectStatus.ACTIVE,
        server_default=ProjectStatus.ACTIVE.value,
    )
    # RESTRICT: muốn xóa workspace thì phải xóa hết project bên trong trước (tránh xóa nhầm cả cây)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"), index=True
    )
    # Chỉ để biết ai tạo, KHÔNG dùng để phân quyền (quyền đi theo role trong workspace)
    creator_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )

    workspace: Mapped[Workspace] = relationship(back_populates="projects")
    creator: Mapped[User] = relationship(back_populates="created_projects")
    # cascade="all, delete-orphan": xóa project -> xóa luôn các task thuộc project
    tasks: Mapped[list[Task]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="Task.id"
    )
