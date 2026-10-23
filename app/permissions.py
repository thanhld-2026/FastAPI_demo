"""Quy tắc phân quyền nghiệp vụ, viết dưới dạng hàm thuần (trả về True/False).

Tách khỏi FastAPI để dễ đọc, dễ test và dùng lại ở nhiều nơi (dependencies, services).

Hai tầng vai trò (RBAC):
- UserRole (toàn hệ thống): ADMIN làm được mọi thứ ở mọi workspace; MEMBER thì tùy role
  trong từng workspace.
- WorkspaceRole (trong 1 workspace): VIEWER < EDITOR < OWNER. Cùng 1 user có thể là OWNER
  ở workspace A nhưng chỉ là VIEWER ở workspace B.

| Hành động                                              | Role tối thiểu                  |
|--------------------------------------------------------|---------------------------------|
| Đọc workspace / project / task / comment / activity     | VIEWER                          |
| Bookmark task (dữ liệu cá nhân)                         | VIEWER                          |
| Tạo / sửa / assign task, thêm comment                   | EDITOR                          |
| Xóa task                                                | OWNER, hoặc người tạo (EDITOR)  |
| Sửa / xóa comment                                       | OWNER, hoặc tác giả (EDITOR)    |
| Được giao task                                          | EDITOR                          |
| Tạo / sửa / archive / xóa project, quản lý member, workspace | OWNER                      |

Không phải thành viên workspace thì không thấy gì (API trả 404, xem dependencies.py).
"""

from app.models import Comment, Task, User, UserRole, WorkspaceRole

_ROLE_RANK = {WorkspaceRole.VIEWER: 1, WorkspaceRole.EDITOR: 2, WorkspaceRole.OWNER: 3}


def is_admin(user: User) -> bool:
    return user.role == UserRole.ADMIN


def _at_least(role: WorkspaceRole | None, minimum: WorkspaceRole) -> bool:
    return role is not None and _ROLE_RANK[role] >= _ROLE_RANK[minimum]


def has_role(user: User, role: WorkspaceRole | None, minimum: WorkspaceRole) -> bool:
    """`role`: role của user trong workspace đang xét (None = không phải thành viên)."""
    return is_admin(user) or _at_least(role, minimum)


def can_delete_task(user: User, role: WorkspaceRole | None, task: Task) -> bool:
    if has_role(user, role, WorkspaceRole.OWNER):
        return True
    return task.creator_id == user.id and has_role(user, role, WorkspaceRole.EDITOR)


def can_modify_comment(user: User, role: WorkspaceRole | None, comment: Comment) -> bool:
    """Tác giả chỉ sửa / xóa được khi vẫn còn quyền EDITOR (bị hạ xuống VIEWER thì thôi)."""
    if has_role(user, role, WorkspaceRole.OWNER):
        return True
    return comment.author_id == user.id and has_role(user, role, WorkspaceRole.EDITOR)


def can_be_assigned(role: WorkspaceRole | None) -> bool:
    """Chỉ giao task cho người làm được task: thành viên từ EDITOR trở lên (admin cũng phải là
    thành viên, vì task giao cho người ngoài workspace thì người đó không đọc được)."""
    return _at_least(role, WorkspaceRole.EDITOR)


def can_remove_member(user: User, role: WorkspaceRole | None, target_user_id: int) -> bool:
    """OWNER xóa được thành viên khác; thành viên tự rời workspace được."""
    return target_user_id == user.id or has_role(user, role, WorkspaceRole.OWNER)
