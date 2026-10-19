from fastapi import APIRouter, HTTPException, status

from app import crud
from app.dependencies import DbSession
from app.schemas.project import ProjectOut

router = APIRouter(prefix="/api/projects", tags=["Projects"])


@router.get("", response_model=list[ProjectOut], summary="Danh sách project")
def list_projects(db: DbSession):
    return crud.project.list_projects(db)


@router.get("/{project_id}", response_model=ProjectOut, summary="Chi tiết project")
def get_project(project_id: int, db: DbSession):
    project = crud.project.get(db, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project
