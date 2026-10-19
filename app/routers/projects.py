from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app import crud
from app.dependencies import DbSession, get_project_or_404, load_tags_or_400
from app.models import Project
from app.schemas.project import ProjectDetail, ProjectOut
from app.schemas.task import TaskCreate, TaskOut

router = APIRouter(prefix="/api/projects", tags=["Projects"])


@router.get("", response_model=list[ProjectOut], summary="Danh sách project")
def list_projects(db: DbSession):
    return crud.project.list_projects(db)


@router.get(
    "/{project_id}", response_model=ProjectDetail, summary="Chi tiết project (kèm danh sách task)"
)
def get_project(project_id: int, db: DbSession):
    project = crud.project.get_detail(db, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


@router.get(
    "/{project_id}/tasks", response_model=list[TaskOut], summary="Danh sách task của project"
)
def list_project_tasks(project: Annotated[Project, Depends(get_project_or_404)], db: DbSession):
    return crud.task.list_for_project(db, project.id)


@router.post(
    "/{project_id}/tasks",
    response_model=TaskOut,
    status_code=status.HTTP_201_CREATED,
    summary="Tạo task trong project",
)
def create_project_task(
    data: TaskCreate,
    project: Annotated[Project, Depends(get_project_or_404)],
    db: DbSession,
):
    creator = crud.user.get_by_id(db, data.creator_id)
    if creator is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Creator not found")
    tags = load_tags_or_400(db, data.tag_ids)
    return crud.task.create(db, project=project, data=data, tags=tags, creator=creator)
