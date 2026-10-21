"""Các Enum dùng chung cho model (DB) và schema (API).

Enum lưu dạng VARCHAR không có CHECK constraint (xem models/base.py: enum_column), nên thêm
giá trị mới không cần migration. Lưu ý khi triển khai: đã có dòng mang giá trị mới (vd
IN_REVIEW) mà rollback app về bản cũ thì bản cũ đọc ra sẽ lỗi (LookupError -> 500).
Muốn rollback an toàn phải chuyển các dòng đó về giá trị cũ trước.
"""

from enum import StrEnum


class UserRole(StrEnum):
    ADMIN = "admin"
    MEMBER = "member"


class WorkspaceRole(StrEnum):
    """Vai trò của user TRONG 1 workspace (khác UserRole là vai trò toàn hệ thống).

    VIEWER < EDITOR < OWNER: role cao hơn có mọi quyền của role thấp hơn (xem permissions.py).
    """

    OWNER = "OWNER"  # người tạo workspace: quản lý workspace, member, project
    EDITOR = "EDITOR"  # làm việc với task / comment
    VIEWER = "VIEWER"  # chỉ đọc


class TaskStatus(StrEnum):
    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    IN_REVIEW = "IN_REVIEW"
    DONE = "DONE"


class TaskPriority(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    URGENT = "URGENT"


class ProjectStatus(StrEnum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"  # task / comment trong project chỉ còn đọc được


class ActivityAction(StrEnum):
    CREATED = "created"
    UPDATED = "updated"
    ASSIGNED = "assigned"
    COMMENTED = "commented"
