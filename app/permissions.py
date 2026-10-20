"""Quy tắc phân quyền nghiệp vụ, viết dưới dạng hàm thuần (trả về True/False).

Tách khỏi FastAPI để dễ đọc, dễ test và dùng lại ở nhiều router.

Quy ước vai trò:
- Admin: role = "admin", làm được mọi thứ.
- PM (Project Manager): owner của project (người tạo project). Một user có thể là PM
  của project A nhưng chỉ là member bình thường ở project B.
"""

from app.models import Comment, Project, Task, User, UserRole


def is_admin(user: User) -> bool:
    return user.role == UserRole.ADMIN


def can_manage_project(user: User, project: Project) -> bool:
    """Admin hoặc PM của project: sửa/xóa project, assign task."""
    return is_admin(user) or project.owner_id == user.id


def can_edit_task(user: User, task: Task) -> bool:
    """Admin, PM, người tạo task hoặc người được assign."""
    return can_manage_project(user, task.project) or user.id in (task.creator_id, task.assignee_id)


def can_delete_task(user: User, task: Task) -> bool:
    """Admin, PM hoặc người tạo task."""
    return can_manage_project(user, task.project) or user.id == task.creator_id


def can_modify_comment(user: User, comment: Comment) -> bool:
    """Chỉ người viết comment, Admin hoặc PM của project chứa task mới được sửa/xóa."""
    return comment.author_id == user.id or can_manage_project(user, comment.task.project)
