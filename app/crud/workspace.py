from sqlalchemy import ColumnElement, Select, exists, func, select, true
from sqlalchemy.orm import InstrumentedAttribute, Session, joinedload, selectinload

from app import permissions
from app.models import Project, Task, User, Workspace, WorkspaceMember, WorkspaceRole
from app.schemas.common import PageParams
from app.schemas.workspace import WorkspaceCreate, WorkspaceUpdate


def member_workspace_ids(user_id: int) -> Select[int]:
    """Subquery id các workspace user là thành viên."""
    return select(WorkspaceMember.workspace_id).where(WorkspaceMember.user_id == user_id)


def visible_to(
    viewer: User | None, workspace_id: InstrumentedAttribute[int]
) -> ColumnElement[bool]:
    """Điều kiện lọc dữ liệu (project, task, bookmark, profile...) theo workspace người xem là
    thành viên. Dùng chung cho mọi danh sách để không chỗ nào quên lọc.

    - viewer=None: tầng trên đã kiểm tra quyền (vd task của 1 project cụ thể) -> không lọc.
    - Admin hệ thống thấy mọi workspace.
    """
    if viewer is None or permissions.is_admin(viewer):
        return true()
    return workspace_id.in_(member_workspace_ids(viewer.id))


# ---------- Role của user (None = không phải thành viên) ----------
def get_role(db: Session, workspace_id: int, user_id: int) -> WorkspaceRole | None:
    stmt = select(WorkspaceMember.role).where(
        WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.user_id == user_id
    )
    return db.scalar(stmt)


def get_role_for_project(db: Session, project_id: int, user_id: int) -> WorkspaceRole | None:
    """Role của user trong workspace chứa project, 1 query JOIN (không cần load project)."""
    stmt = (
        select(WorkspaceMember.role)
        .join(Project, Project.workspace_id == WorkspaceMember.workspace_id)
        .where(Project.id == project_id, WorkspaceMember.user_id == user_id)
    )
    return db.scalar(stmt)


def get_role_for_task(db: Session, task_id: int, user_id: int) -> WorkspaceRole | None:
    """Role của user trong workspace chứa task. None nếu task không tồn tại hoặc không phải
    thành viên -> 2 trường hợp gộp làm 1, đúng với ý đồ trả 404 cho người ngoài."""
    stmt = (
        select(WorkspaceMember.role)
        .join(Project, Project.workspace_id == WorkspaceMember.workspace_id)
        .join(Task, Task.project_id == Project.id)
        .where(Task.id == task_id, WorkspaceMember.user_id == user_id)
    )
    return db.scalar(stmt)


# ---------- Workspace ----------
def get(db: Session, workspace_id: int) -> Workspace | None:
    return db.get(Workspace, workspace_id)


def get_detail(db: Session, workspace_id: int) -> Workspace | None:
    """Workspace + owner + danh sách member (kèm user), số query cố định."""
    stmt = (
        select(Workspace)
        .where(Workspace.id == workspace_id)
        .options(
            joinedload(Workspace.owner),
            selectinload(Workspace.members).joinedload(WorkspaceMember.user),
        )
    )
    return db.scalar(stmt)


def list_for_user(
    db: Session, user: User, pagination: PageParams
) -> tuple[list[Workspace], int]:
    """Workspace user là thành viên (admin: mọi workspace)."""
    conditions = [visible_to(user, Workspace.id)]
    total = db.execute(
        select(func.count()).select_from(Workspace).where(*conditions)
    ).scalar_one()
    stmt = (
        select(Workspace)
        .where(*conditions)
        .options(joinedload(Workspace.owner))
        .order_by(Workspace.id)
        .offset(pagination.offset)
        .limit(pagination.limit)
    )
    return list(db.scalars(stmt).all()), total


def create(db: Session, data: WorkspaceCreate, owner: User) -> Workspace:
    """Tạo workspace + membership OWNER của người tạo trong cùng 1 commit."""
    workspace = Workspace(name=data.name, owner=owner)
    workspace.members.append(WorkspaceMember(user=owner, role=WorkspaceRole.OWNER))
    db.add(workspace)
    db.commit()
    return workspace


def update(db: Session, workspace: Workspace, data: WorkspaceUpdate) -> Workspace:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(workspace, field, value)
    db.commit()
    db.refresh(workspace)
    return workspace


def has_projects(db: Session, workspace_id: int) -> bool:
    return bool(db.scalar(select(exists().where(Project.workspace_id == workspace_id))))


def delete(db: Session, workspace: Workspace) -> None:
    db.delete(workspace)  # cascade xóa luôn workspace_members
    db.commit()


# ---------- Member ----------
def get_member(db: Session, workspace_id: int, user_id: int) -> WorkspaceMember | None:
    stmt = (
        select(WorkspaceMember)
        .where(WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.user_id == user_id)
        .options(joinedload(WorkspaceMember.user))
    )
    return db.scalar(stmt)


def add_member(db: Session, *, workspace_id: int, user: User, role: WorkspaceRole) -> None:
    """Thêm vào session, KHÔNG commit (service commit, bắt IntegrityError khi trùng)."""
    db.add(WorkspaceMember(workspace_id=workspace_id, user=user, role=role))


def set_member_role(db: Session, member: WorkspaceMember, role: WorkspaceRole) -> None:
    member.role = role
    db.commit()


def delete_member(db: Session, member: WorkspaceMember) -> None:
    """KHÔNG commit: service commit cùng việc bỏ assign các task của member."""
    db.delete(member)
