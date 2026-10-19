"""Các dependency dùng chung (hệ thống Dependency Injection của FastAPI)."""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import crud
from app.database import get_db
from app.models import Project, Tag, Task

DbSession = Annotated[Session, Depends(get_db)]


# ---------- Load resource theo path param ----------
def get_project_or_404(project_id: int, db: DbSession) -> Project:
    project = crud.project.get(db, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


def get_task_or_404(task_id: int, db: DbSession) -> Task:
    task = crud.task.get(db, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


TaskDep = Annotated[Task, Depends(get_task_or_404)]


# ---------- Helper dùng chung cho router ----------
def load_tags_or_400(db: Session, tag_ids: list[int]) -> list[Tag]:
    """Body tham chiếu tới tag không tồn tại -> 400 (khác 404 dành cho resource trên URL)."""
    tags = crud.tag.get_many(db, tag_ids)
    missing = set(tag_ids) - {tag.id for tag in tags}
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tag ids not found: {sorted(missing)}",
        )
    return tags
