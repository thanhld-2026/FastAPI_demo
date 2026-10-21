"""Tách riêng file để tránh import vòng (user <-> project <-> task)."""

from datetime import datetime

from app.schemas.common import ORMSchema
from app.schemas.project import ProjectBrief
from app.schemas.task import TaskBrief


class UserProfile(ORMSchema):
    id: int
    username: str
    full_name: str | None
    bio: str | None
    created_at: datetime
    created_projects: list[ProjectBrief]
    assigned_tasks: list[TaskBrief]
