"""Import toàn bộ model tại đây để:

1. SQLAlchemy resolve được các relationship khai báo bằng tên chuỗi ("Task", "User", ...).
2. Alembic (alembic/env.py) chỉ cần `import app.models` là thấy đủ bảng khi autogenerate.
"""

from app.models.activity import TaskActivity
from app.models.associations import task_bookmarks, task_tags
from app.models.comment import Comment
from app.models.enums import ActivityAction, ProjectStatus, TaskPriority, TaskStatus, UserRole
from app.models.project import Project
from app.models.tag import Tag
from app.models.task import Task
from app.models.user import User

__all__ = [
    "ActivityAction",
    "Comment",
    "Project",
    "ProjectStatus",
    "Tag",
    "Task",
    "TaskActivity",
    "TaskPriority",
    "TaskStatus",
    "User",
    "UserRole",
    "task_bookmarks",
    "task_tags",
]
