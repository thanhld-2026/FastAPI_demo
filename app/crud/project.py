from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Project


def get(db: Session, project_id: int) -> Project | None:
    return db.get(Project, project_id)


def list_projects(db: Session) -> list[Project]:
    return list(db.scalars(select(Project).order_by(Project.id)).all())
