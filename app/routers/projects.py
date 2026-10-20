from typing import Annotated

from fastapi import APIRouter, Query, status

from app import crud
from app.core import messages
from app.core.exceptions import NotFoundException
from app.core.responses import error_responses
from app.dependencies import (
    CurrentUser,
    DbSession,
    ManagedProject,
    Pagination,
    ProjectDep,
    get_tags_by_ids,
)
from app.models import TaskPriority, TaskStatus
from app.schemas.common import Page
from app.schemas.project import ProjectCreate, ProjectDetail, ProjectOut, ProjectUpdate
from app.schemas.task import TaskCreate, TaskOut

router = APIRouter(prefix="/projects", tags=["Projects"])


@router.get("", response_model=Page[ProjectOut], summary="Danh sách project")
def list_projects(db: DbSession, pagination: Pagination):
    items, total = crud.project.list_projects(db, pagination)
    return Page.build(items, total, pagination)


@router.post(
    "",
    response_model=ProjectOut,
    status_code=status.HTTP_201_CREATED,
    summary="Tạo project (người tạo trở thành PM)",
    responses=error_responses(401, 403),
)
def create_project(data: ProjectCreate, current_user: CurrentUser, db: DbSession):
    return crud.project.create(db, data, owner=current_user)


@router.get(
    "/{project_id}",
    response_model=ProjectDetail,
    summary="Chi tiết project (kèm danh sách task)",
    responses=error_responses(404),
)
def get_project(project_id: int, db: DbSession):
    project = crud.project.get_detail(db, project_id)
    if project is None:
        raise NotFoundException(messages.PROJECT_NOT_FOUND)
    return project


@router.put(
    "/{project_id}",
    response_model=ProjectOut,
    summary="[PM/Admin] Cập nhật project",
    responses=error_responses(401, 403, 404),
)
def update_project(data: ProjectUpdate, project: ManagedProject, db: DbSession):
    return crud.project.update(db, project, data)


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="[PM/Admin] Xóa project",
    responses=error_responses(401, 403, 404),
)
def delete_project(project: ManagedProject, db: DbSession):
    crud.project.delete(db, project)


@router.get(
    "/{project_id}/tasks",
    response_model=Page[TaskOut],
    summary="Danh sách task của project (lọc + phân trang)",
    responses=error_responses(404),
)
def list_project_tasks(
    project: ProjectDep,
    db: DbSession,
    pagination: Pagination,
    # alias="status": trên URL vẫn là ?status=..., đặt tên biến khác để không đè module `status`
    task_status: Annotated[TaskStatus | None, Query(alias="status")] = None,
    priority: TaskPriority | None = None,
):
    items, total = crud.task.list_tasks(
        db,
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
    summary="Tạo task trong project",
    responses=error_responses(400, 401, 403, 404),
)
def create_project_task(
    data: TaskCreate, project: ProjectDep, current_user: CurrentUser, db: DbSession
):
    tags = get_tags_by_ids(db, data.tag_ids)
    return crud.task.create(db, project=project, data=data, tags=tags, creator=current_user)
