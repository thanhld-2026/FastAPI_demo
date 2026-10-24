"""Import toàn bộ model tại đây để:

1. SQLAlchemy resolve được các relationship khai báo bằng tên chuỗi ("Task", "User", ...).
2. Alembic (alembic/env.py) chỉ cần `import app.models` là thấy đủ bảng khi autogenerate.
"""

from app.models.activity import TaskActivity
from app.models.associations import task_bookmarks, task_labels
from app.models.comment import Comment
from app.models.enums import (
    ActivityAction,
    ProjectStatus,
    TaskPriority,
    TaskStatus,
    UserRole,
    WorkspaceRole,
)
from app.models.label import Label
from app.models.project import Project
from app.models.refresh_token import RefreshToken
from app.models.task import Task
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember

__all__ = [
    "ActivityAction",
    "Comment",
    "Label",
    "Project",
    "ProjectStatus",
    "RefreshToken",
    "Task",
    "TaskActivity",
    "TaskPriority",
    "TaskStatus",
    "User",
    "UserRole",
    "Workspace",
    "WorkspaceMember",
    "WorkspaceRole",
    "task_bookmarks",
    "task_labels",
]

# Đăng ký event của SQLAlchemy Session tự làm mới cache danh sách task (services/task_cache.py).
# Đặt ở đây (không phải ở service) để MỌI process dùng model đều có: API, script, worker...
# Import cuối file: các model ở trên đã khai báo xong nên không bị import vòng.
from app.services import task_cache as _task_cache  # noqa: F401
