from fastapi import APIRouter, status
from sqlalchemy.exc import IntegrityError

from app import crud, permissions
from app.core import messages
from app.core.exceptions import ForbiddenException, NotFoundException
from app.core.responses import error_responses
from app.dependencies import (
    CurrentUser,
    DbSession,
    OwnedWorkspace,
    Pagination,
    ReadableWorkspace,
)
from app.schemas.common import Page
from app.schemas.project import ProjectCreate, ProjectOut
from app.schemas.workspace import (
    MemberInvite,
    MemberRoleUpdate,
    WorkspaceCreate,
    WorkspaceDetail,
    WorkspaceMemberOut,
    WorkspaceOut,
    WorkspaceUpdate,
)
from app.services import workspaces as workspace_service

router = APIRouter(prefix="/workspaces", tags=["Workspaces"])


@router.post(
    "",
    response_model=WorkspaceDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Tạo workspace (người tạo là OWNER)",
    responses=error_responses(401, 403),
)
def create_workspace(data: WorkspaceCreate, current_user: CurrentUser, db: DbSession):
    workspace = crud.workspace.create(db, data, owner=current_user)
    return crud.workspace.get_detail(db, workspace.id)


@router.get(
    "",
    response_model=Page[WorkspaceOut],
    summary="Các workspace tôi là thành viên (admin: tất cả)",
    responses=error_responses(401, 403),
)
def list_workspaces(current_user: CurrentUser, db: DbSession, pagination: Pagination):
    items, total = crud.workspace.list_for_user(db, current_user, pagination)
    return Page.build(items, total, pagination)


@router.get(
    "/{workspace_id}",
    response_model=WorkspaceDetail,
    summary="Chi tiết workspace kèm danh sách thành viên",
    responses=error_responses(401, 403, 404),
)
def get_workspace(workspace: ReadableWorkspace, db: DbSession):
    return crud.workspace.get_detail(db, workspace.id)


@router.patch(
    "/{workspace_id}",
    response_model=WorkspaceOut,
    summary="[OWNER] Đổi tên workspace",
    responses=error_responses(401, 403, 404),
)
def update_workspace(data: WorkspaceUpdate, workspace: OwnedWorkspace, db: DbSession):
    return crud.workspace.update(db, workspace, data)


@router.delete(
    "/{workspace_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="[OWNER] Xóa workspace (phải xóa hết project trước, nếu không -> 409)",
    responses=error_responses(401, 403, 404, 409),
)
def delete_workspace(workspace: OwnedWorkspace, db: DbSession):
    workspace_service.delete_workspace(db, workspace)


# ---------- Thành viên ----------
@router.post(
    "/{workspace_id}/members",
    response_model=WorkspaceMemberOut,
    status_code=status.HTTP_201_CREATED,
    summary="[OWNER] Mời thành viên theo email (role EDITOR / VIEWER)",
    responses=error_responses(400, 401, 403, 404, 409),
)
def invite_member(data: MemberInvite, workspace: OwnedWorkspace, db: DbSession):
    return workspace_service.invite_member(
        db, workspace=workspace, email=str(data.email), role=data.role
    )


@router.patch(
    "/{workspace_id}/members/{user_id}",
    response_model=WorkspaceMemberOut,
    summary="[OWNER] Đổi role của thành viên",
    responses=error_responses(400, 401, 403, 404),
)
def change_member_role(
    user_id: int,
    data: MemberRoleUpdate,
    current_user: CurrentUser,
    workspace: OwnedWorkspace,
    db: DbSession,
):
    """Hạ xuống VIEWER thì task người đó đang làm (project ACTIVE) được bỏ assign."""
    return workspace_service.change_member_role(
        db, workspace=workspace, user_id=user_id, role=data.role, actor=current_user
    )


@router.delete(
    "/{workspace_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Xóa thành viên (OWNER) hoặc tự rời workspace; task của họ được bỏ assign",
    responses=error_responses(400, 401, 403, 404),
)
def remove_member(
    user_id: int, current_user: CurrentUser, workspace: ReadableWorkspace, db: DbSession
):
    role = crud.workspace.get_role(db, workspace.id, current_user.id)
    if not permissions.can_remove_member(current_user, role, user_id):
        raise ForbiddenException(messages.WORKSPACE_ROLE_REQUIRED.format(role="OWNER"))
    workspace_service.remove_member(db, workspace=workspace, user_id=user_id, actor=current_user)


# ---------- Project trong workspace ----------
@router.post(
    "/{workspace_id}/projects",
    response_model=ProjectOut,
    status_code=status.HTTP_201_CREATED,
    summary="[OWNER] Tạo project trong workspace",
    responses=error_responses(401, 403, 404),
)
def create_project(
    data: ProjectCreate, current_user: CurrentUser, workspace: OwnedWorkspace, db: DbSession
):
    try:
        return crud.project.create(db, data, workspace=workspace, creator=current_user)
    except IntegrityError:
        # Workspace vừa bị xóa bởi request khác: FK workspace_id không còn
        db.rollback()
        raise NotFoundException(messages.WORKSPACE_NOT_FOUND) from None
