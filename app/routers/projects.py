from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app import crud
from app.dependencies import (
    CurrentUser,
    DbSession,
    ManagedProject,
    get_project_or_404,
    load_tags_or_400,
)
from app.models import Project, TaskPriority, TaskStatus
from app.schemas.common import Page
from app.schemas.project import ProjectCreate, ProjectDetail, ProjectOut, ProjectUpdate
from app.schemas.task import TaskCreate, TaskOut

router = APIRouter(prefix="/api/projects", tags=["Projects"])


@router.get("", response_model=Page[ProjectOut], summary="Danh sách project")
def list_projects(
    db: DbSession,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    items, total = crud.project.list_projects(db, skip=skip, limit=limit)
    return {"items": items, "total": total, "skip": skip, "limit": limit}


@router.post(
    "",
    response_model=ProjectOut,
    status_code=status.HTTP_201_CREATED,
    summary="Tạo project (người tạo trở thành PM)",
)
def create_project(data: ProjectCreate, current_user: CurrentUser, db: DbSession):
    return crud.project.create(db, data, owner=current_user)


@router.get(
    "/{project_id}", response_model=ProjectDetail, summary="Chi tiết project (kèm danh sách task)"
)
def get_project(project_id: int, db: DbSession):
    project = crud.project.get_detail(db, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


@router.put("/{project_id}", response_model=ProjectOut, summary="[PM/Admin] Cập nhật project")
def update_project(data: ProjectUpdate, project: ManagedProject, db: DbSession):
    return crud.project.update(db, project, data)


@router.delete(
    "/{project_id}", status_code=status.HTTP_204_NO_CONTENT, summary="[PM/Admin] Xóa project"
)
def delete_project(project: ManagedProject, db: DbSession):
    crud.project.delete(db, project)


@router.get(
    "/{project_id}/tasks",
    response_model=Page[TaskOut],
    summary="Danh sách task của project (lọc + phân trang)",
)
def list_project_tasks(
    project: Annotated[Project, Depends(get_project_or_404)],
    db: DbSession,
    # alias="status": trên URL vẫn là ?status=..., đặt tên biến khác để không đè module `status`
    task_status: Annotated[TaskStatus | None, Query(alias="status")] = None,
    priority: TaskPriority | None = None,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    items, total = crud.task.list_tasks(
        db, project_id=project.id, status=task_status, priority=priority, skip=skip, limit=limit
    )
    return {"items": items, "total": total, "skip": skip, "limit": limit}


@router.post(
    "/{project_id}/tasks",
    response_model=TaskOut,
    status_code=status.HTTP_201_CREATED,
    summary="Tạo task trong project",
)
def create_project_task(
    data: TaskCreate,
    project: Annotated[Project, Depends(get_project_or_404)],
    current_user: CurrentUser,
    db: DbSession,
):
    tags = load_tags_or_400(db, data.tag_ids)
    return crud.task.create(db, project=project, data=data, tags=tags, creator=current_user)
