from typing import Annotated

from fastapi import APIRouter, Query, status
from pydantic import PositiveInt

from app import crud, permissions
from app.core import messages
from app.core.exceptions import NotFoundException
from app.core.responses import error_responses
from app.dependencies import (
    ChangeableProject,
    CurrentUser,
    DbSession,
    EditableProject,
    ManagedProject,
    Pagination,
    ReadableProject,
    get_labels_by_ids,
)
from app.models import ProjectStatus, TaskPriority, TaskStatus
from app.schemas.common import Page
from app.schemas.project import ProjectDetail, ProjectOut, ProjectUpdate
from app.schemas.task import TaskCreate, TaskOut

router = APIRouter(prefix="/projects", tags=["Projects"])


@router.get(
    "",
    response_model=Page[ProjectOut],
    summary="Project trong các workspace tôi là thành viên",
    responses=error_responses(401, 403),
)
def list_projects(
    # Tạo project: POST /api/v1/workspaces/{workspace_id}/projects
    current_user: CurrentUser,
    db: DbSession,
    pagination: Pagination,
    project_status: Annotated[ProjectStatus | None, Query(alias="status")] = None,
    workspace_id: PositiveInt | None = None,
):
    items, total = crud.project.list_projects(
        db,
        pagination,
        viewer=current_user,
        include_all=permissions.is_admin(current_user),
        status=project_status,
        workspace_id=workspace_id,
    )
    return Page.build(items, total, pagination)


@router.get(
    "/{project_id}",
    response_model=ProjectDetail,
    summary="Chi tiết project (kèm danh sách task)",
    responses=error_responses(401, 403, 404),
)
def get_project(project: ReadableProject, db: DbSession):
    detail = crud.project.get_detail(db, project.id)
    if detail is None:
        raise NotFoundException(messages.PROJECT_NOT_FOUND)
    return detail


@router.put(
    "/{project_id}",
    response_model=ProjectOut,
    summary="[OWNER] Cập nhật project (project đã archive -> 409, unarchive trước)",
    responses=error_responses(401, 403, 404, 409),
)
def update_project(data: ProjectUpdate, project: ChangeableProject, db: DbSession):
    return crud.project.update(db, project, data)


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="[OWNER] Xóa project (project đã archive -> 409, unarchive trước)",
    responses=error_responses(401, 403, 404, 409),
)
def delete_project(project: ChangeableProject, db: DbSession):
    crud.project.delete(db, project)


@router.post(
    "/{project_id}/archive",
    response_model=ProjectOut,
    summary="[OWNER] Archive project (project, task, comment chỉ còn đọc được)",
    responses=error_responses(401, 403, 404),
)
def archive_project(project: ManagedProject, db: DbSession):
    """Idempotent: archive 1 project đã archive vẫn trả 200."""
    return crud.project.set_status(db, project, ProjectStatus.ARCHIVED)


@router.post(
    "/{project_id}/unarchive",
    response_model=ProjectOut,
    summary="[OWNER] Mở lại project đã archive",
    responses=error_responses(401, 403, 404),
)
def unarchive_project(project: ManagedProject, db: DbSession):
    return crud.project.set_status(db, project, ProjectStatus.ACTIVE)


@router.get(
    "/{project_id}/tasks",
    response_model=Page[TaskOut],
    summary="Danh sách task của project (lọc + phân trang)",
    responses=error_responses(401, 403, 404),
)
def list_project_tasks(
    current_user: CurrentUser,
    project: ReadableProject,
    db: DbSession,
    pagination: Pagination,
    # alias="status": trên URL vẫn là ?status=..., đặt tên biến khác để không đè module `status`
    task_status: Annotated[TaskStatus | None, Query(alias="status")] = None,
    priority: TaskPriority | None = None,
):
    items, total = crud.task.list_tasks(
        db,
        viewer=current_user,
        include_all=True,  # ReadableProject đã kiểm tra quyền đọc project này
        project_id=project.id,
        status=task_status,
        priority=priority,
        pagination=pagination,
    )
    return Page.build(items, total, pagination)


@router.post(
    "/{project_id}/tasks",
    response_model=TaskOut,
    status_code=status.HTTP_201_CREATED,
    summary="[EDITOR] Tạo task trong project",
    responses=error_responses(400, 401, 403, 404, 409),
)
def create_project_task(
    data: TaskCreate, current_user: CurrentUser, project: EditableProject, db: DbSession
):
    labels = get_labels_by_ids(db, project.id, data.label_ids)
    return crud.task.create(db, project=project, data=data, labels=labels, creator=current_user)
