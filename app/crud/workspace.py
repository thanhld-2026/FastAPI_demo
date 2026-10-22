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


def get_role_for_project(
    db: Session, project_id: int, user_id: int, *, lock: bool = False
) -> WorkspaceRole | None:
    """Role của user trong workspace chứa project, 1 query JOIN (không cần load project).

    lock: khóa chia sẻ dòng membership (FOR SHARE) tới hết transaction: đổi role / xóa thành
    viên (FOR UPDATE dòng đó) phải chờ. Dùng khi giao task cho user này.
    """
    stmt = (
        select(WorkspaceMember.role)
        .join(Project, Project.workspace_id == WorkspaceMember.workspace_id)
        .where(Project.id == project_id, WorkspaceMember.user_id == user_id)
    )
    if lock:
        stmt = stmt.with_for_update(read=True, of=WorkspaceMember)
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
    """Cascade xóa luôn workspace_members. Còn project thì FK RESTRICT chặn (IntegrityError)."""
    db.delete(workspace)
    db.commit()


# ---------- Member ----------
def get_member(
    db: Session, workspace_id: int, user_id: int, *, lock: bool = False
) -> WorkspaceMember | None:
    """lock: SELECT ... FOR UPDATE dòng membership + đọc lại, dùng khi đổi role / xóa thành viên
    (giao task cho người này cùng lúc phải chờ, xem get_role_for_project)."""
    stmt = (
        select(WorkspaceMember)
        .where(WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.user_id == user_id)
        .options(joinedload(WorkspaceMember.user))
    )
    if lock:
        stmt = stmt.with_for_update(of=WorkspaceMember).execution_options(
            populate_existing=True
        )
    return db.scalar(stmt)


def member_user_ids(db: Session, workspace_id: int, user_ids: set[int]) -> set[int]:
    """Những user trong `user_ids` hiện còn là thành viên workspace."""
    stmt = select(WorkspaceMember.user_id).where(
        WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.user_id.in_(user_ids)
    )
    return set(db.scalars(stmt).all())


def add_member(db: Session, *, workspace_id: int, user: User, role: WorkspaceRole) -> None:
    """Thêm vào session, KHÔNG commit (service commit, bắt IntegrityError khi trùng)."""
    db.add(WorkspaceMember(workspace_id=workspace_id, user=user, role=role))


def delete_member(db: Session, member: WorkspaceMember) -> None:
    """KHÔNG commit: service commit cùng việc bỏ assign các task của member."""
    db.delete(member)
