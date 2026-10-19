from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models import Project, Task


def get(db: Session, project_id: int) -> Project | None:
    return db.get(Project, project_id)


def get_detail(db: Session, project_id: int) -> Project | None:
    """Project + owner + tasks + assignee của từng task.

    - joinedload(owner): quan hệ Many-to-One -> JOIN luôn trong câu query chính.
    - selectinload(tasks): quan hệ One-to-Many -> 1 query phụ `WHERE project_id IN (...)`,
      tránh JOIN làm nhân bản dòng của project.
    - .joinedload(Task.assignee): load lồng tiếp assignee của mỗi task (chained loading).
    => Tổng cộng 2 query dù project có 1 hay 1000 task.
    """
    stmt = (
        select(Project)
        .where(Project.id == project_id)
        .options(
            joinedload(Project.owner),
            selectinload(Project.tasks).joinedload(Task.assignee),
        )
    )
    return db.scalar(stmt)


def list_projects(db: Session) -> list[Project]:
    stmt = (
        select(Project)
        .options(joinedload(Project.owner))  # tránh N+1 khi trả về owner của từng project
        .order_by(Project.id)
    )
    return list(db.scalars(stmt).all())
