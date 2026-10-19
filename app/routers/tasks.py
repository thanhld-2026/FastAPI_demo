from fastapi import APIRouter

from app.dependencies import TaskDep
from app.schemas.task import TaskOut

router = APIRouter(prefix="/api/tasks", tags=["Tasks"])


@router.get("/{task_id}", response_model=TaskOut, summary="Chi tiết task")
def get_task(task: TaskDep):
    return task
