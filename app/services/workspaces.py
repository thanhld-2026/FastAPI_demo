"""Nghiệp vụ workspace: mời / đổi role / xóa thành viên, xóa workspace."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import crud
from app.core import messages
from app.core.exceptions import BadRequestException, ConflictException, NotFoundException
from app.models import (
    ActivityAction,
    Project,
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


def _get_non_owner_member(db: Session, workspace: Workspace, user_id: int) -> WorkspaceMember:
    member = crud.workspace.get_member(db, workspace.id, user_id)
    if member is None:
        raise NotFoundException(messages.MEMBER_NOT_FOUND)
    if user_id == workspace.owner_id:
        raise BadRequestException(messages.OWNER_MEMBERSHIP_LOCKED)
    return member


def change_member_role(
    db: Session, *, workspace: Workspace, user_id: int, role: WorkspaceRole
) -> WorkspaceMember:
    member = _get_non_owner_member(db, workspace, user_id)
    crud.workspace.set_member_role(db, member, role)
    return member


def remove_member(db: Session, *, workspace: Workspace, user_id: int, actor: User) -> None:
    """Xóa thành viên + bỏ assign các task của họ trong workspace (có ghi activity), 1 commit.

    Người ngoài workspace không đọc được task nữa, để họ đứng tên assignee là sai dữ liệu.
    """
    member = _get_non_owner_member(db, workspace, user_id)
    assigned = db.scalars(
        select(Task)
        .join(Project, Project.id == Task.project_id)
        .where(Project.workspace_id == workspace.id, Task.assignee_id == user_id)
    ).all()
    for task in assigned:
        task.assignee = None
        crud.activity.add(
            db,
            task=task,
            actor=actor,
            action=ActivityAction.ASSIGNED,
            detail=f"unassigned ({member.user.full_name} left the workspace)",
        )
    crud.workspace.delete_member(db, member)
    db.commit()


def delete_workspace(db: Session, workspace: Workspace) -> None:
    if crud.workspace.has_projects(db, workspace.id):
        raise ConflictException(messages.WORKSPACE_HAS_PROJECTS)
    crud.workspace.delete(db, workspace)
