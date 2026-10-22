"""Nghiệp vụ workspace: mời / đổi role / xóa thành viên, xóa workspace."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import crud, permissions
from app.core import messages
from app.core.exceptions import BadRequestException, ConflictException, NotFoundException
from app.models import (
    ActivityAction,
    Project,
    ProjectStatus,
    Task,
    User,
    Workspace,
    WorkspaceMember,
    WorkspaceRole,
)


def invite_member(
    db: Session, *, workspace: Workspace, email: str, role: WorkspaceRole
) -> WorkspaceMember:
    invitee = crud.user.get_by_email(db, email)
    if invitee is None or not invitee.is_active:
        # Body tham chiếu dữ liệu không tồn tại -> 400 (404 dành cho resource trên URL)
        raise BadRequestException(messages.INVITEE_NOT_FOUND)
    if crud.workspace.get_member(db, workspace.id, invitee.id) is not None:
        raise ConflictException(messages.ALREADY_MEMBER)
    try:
        crud.workspace.add_member(db, workspace_id=workspace.id, user=invitee, role=role)
        db.commit()
    except IntegrityError:
        # 2 request mời cùng 1 người đồng thời: khóa chính (workspace_id, user_id) chặn request sau
        db.rollback()
        raise ConflictException(messages.ALREADY_MEMBER) from None
    member = crud.workspace.get_member(db, workspace.id, invitee.id)
    assert member is not None
    return member


def _get_member_for_change(db: Session, workspace: Workspace, user_id: int) -> WorkspaceMember:
    """Thành viên (khác OWNER) sắp bị đổi role / xóa, khóa dòng membership tới khi commit."""
    member = crud.workspace.get_member(db, workspace.id, user_id, lock=True)
    if member is None:
        raise NotFoundException(messages.MEMBER_NOT_FOUND)
    if member.role == WorkspaceRole.OWNER:
        raise BadRequestException(messages.OWNER_MEMBERSHIP_LOCKED)
    return member


def _unassign_tasks(db: Session, *, member: WorkspaceMember, actor: User, reason: str) -> None:
    """Bỏ assign task của `member` trong các project ACTIVE của workspace (có ghi activity).

    Chỉ EDITOR trở lên mới được giao task, mất quyền đó thì task phải trả lại để giao người khác.
    Project đã archive là chỉ đọc nên giữ nguyên (lịch sử ai từng làm task). FOR SHARE các dòng
    project để archive không chen vào giữa chừng.
    """
    tasks = db.scalars(
        select(Task)
        .join(Project, Project.id == Task.project_id)
        .where(
            Project.workspace_id == member.workspace_id,
            Project.status == ProjectStatus.ACTIVE,
            Task.assignee_id == member.user_id,
        )
        .with_for_update(read=True, of=Project)
    ).all()
    for task in tasks:
        task.assignee = None
        crud.activity.add(
            db,
            task=task,
            actor=actor,
            action=ActivityAction.ASSIGNED,
            detail=f"unassigned ({member.user.full_name} {reason})",
        )


def change_member_role(
    db: Session, *, workspace: Workspace, user_id: int, role: WorkspaceRole, actor: User
) -> WorkspaceMember:
    member = _get_member_for_change(db, workspace, user_id)
    if member.role != role and not permissions.can_be_assigned(role):
        _unassign_tasks(db, member=member, actor=actor, reason=f"is now {role.value}")
    member.role = role
    db.commit()
    return member


def remove_member(db: Session, *, workspace: Workspace, user_id: int, actor: User) -> None:
    """Xóa thành viên (hoặc tự rời) + bỏ assign task của họ, trong cùng 1 commit.

    Người ngoài workspace không đọc được task nữa, để họ đứng tên assignee là sai dữ liệu.
    """
    member = _get_member_for_change(db, workspace, user_id)
    reason = "left the workspace" if actor.id == user_id else "was removed from the workspace"
    _unassign_tasks(db, member=member, actor=actor, reason=reason)
    crud.workspace.delete_member(db, member)
    db.commit()


def delete_workspace(db: Session, workspace: Workspace) -> None:
    if crud.workspace.has_projects(db, workspace.id):
        raise ConflictException(messages.WORKSPACE_HAS_PROJECTS)
    try:
        crud.workspace.delete(db, workspace)
    except IntegrityError:
        # Project được tạo cùng lúc (sau bước kiểm tra trên): FK RESTRICT chặn việc xóa
        db.rollback()
        raise ConflictException(messages.WORKSPACE_HAS_PROJECTS) from None
